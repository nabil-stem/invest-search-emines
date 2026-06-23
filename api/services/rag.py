"""Local RAG service backed by Ollama embeddings and project files.

Provides semantic search (Ollama embeddings) with a BM25-style lexical fallback
so that chat always works even when Ollama embedding is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from api.services.llm.model_select import ollama_models as _ollama_models
from api.services.llm.model_select import pick_chat_model as choose_chat_model

ROOT = Path(__file__).resolve().parents[2]
RAG_DIR = ROOT / ".rag"
INDEX_PATH = RAG_DIR / "index.json"
INDEX_VERSION = 4
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT_SECONDS = float(os.environ.get("RAG_EMBED_TIMEOUT_SECONDS", "20"))
SKIP_EMBEDDINGS = os.environ.get("RAG_SKIP_EMBEDDINGS", "0").lower() in {"1", "true", "yes"}

INCLUDE_EXTENSIONS = {".md", ".py", ".csv", ".json", ".geojson", ".txt"}
EXCLUDE_PARTS = {
    ".git",
    ".rag",
    "__pycache__",
    "node_modules",
    "dist",
    ".venv",
    "venv",
}
MAX_TEXT_CHARS = 2600
DEFAULT_MAX_CHUNKS = int(os.environ.get("RAG_MAX_CHUNKS", "220"))
CHAT_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_CHAT_TIMEOUT", "45"))
CHAT_CONTEXT_LIMIT = int(os.environ.get("RAG_CHAT_CONTEXT_LIMIT", "2"))
CHAT_CONTEXT_CHARS = int(os.environ.get("RAG_CHAT_CONTEXT_CHARS", "450"))

# Retrieval fusion config.
#   RAG_HYBRID_MODE: "rrf" (fuse semantic+lexical), "semantic", or "lexical".
#   RAG_RRF_K: Reciprocal Rank Fusion damping constant (higher = flatter weighting).
#   RAG_CANDIDATE_MULTIPLIER: how many candidates each ranker contributes before fusion.
HYBRID_MODE = os.environ.get("RAG_HYBRID_MODE", "rrf").lower()
RRF_K = int(os.environ.get("RAG_RRF_K", "60"))
CANDIDATE_MULTIPLIER = int(os.environ.get("RAG_CANDIDATE_MULTIPLIER", "3"))
# Max chunks from any single source file in the final result set. Stops one
# verbose document (e.g. the long research note) from monopolising every slot
# and starving more specific files. 0 disables the cap. Default 1 measured best
# on the current ~70-chunk / 9-file corpus (retrieval eval: Hit@5 0.6 -> 0.9);
# raise toward 2 as the corpus grows and per-file depth matters more.
MAX_PER_SOURCE = int(os.environ.get("RAG_MAX_PER_SOURCE", "1"))

_index_cache: dict[str, Any] | None = None
_index_mtime: float = 0.0
MOJIBAKE_MARKERS = ("Ã", "Â", "â")
MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u0080\u0099": "’",
    "\u00e2\u0080\u0098": "‘",
    "\u00e2\u0080\u009c": "“",
    "\u00e2\u0080\u009d": "”",
    "\u00e2\u0080\u0093": "–",
    "\u00e2\u0080\u0094": "—",
    "\u00e2\u0080\u00a6": "…",
    "\u00c2\u00a0": " ",
    "Ã©": "é",
    "Ã¨": "è",
    "Ãª": "ê",
    "Ã«": "ë",
    "Ã ": "à",
    "Ã¢": "â",
    "Ã¹": "ù",
    "Ã»": "û",
    "Ã´": "ô",
    "Ã®": "î",
    "Ã¯": "ï",
    "Ã§": "ç",
    "Ã‰": "É",
    "Ãˆ": "È",
    "Ã€": "À",
    "Â·": "·",
}


@dataclass
class RagChunk:
    id: str
    title: str
    source_path: str
    kind: str
    text: str
    embedding: list[float] | None = None


def _project_files() -> list[Path]:
    files = []
    for current_root, directories, filenames in os.walk(ROOT):
        directories[:] = [
            name
            for name in directories
            if name not in EXCLUDE_PARTS and not name.startswith(".api")
        ]
        for filename in filenames:
            path = Path(current_root) / filename
            if path.suffix.lower() not in INCLUDE_EXTENSIONS:
                continue
            if path.name in {"package-lock.json", "tsconfig.tsbuildinfo"}:
                continue
            files.append(path)
    return sorted(files)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return path.read_text(encoding=encoding, errors="replace")
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def _repair_mojibake(text: str) -> str:
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        repaired = text
        for bad, good in MOJIBAKE_REPLACEMENTS.items():
            repaired = repaired.replace(bad, good)
        return repaired


def _migrate_index(index: dict[str, Any]) -> dict[str, Any]:
    for record in index.get("records", []):
        if isinstance(record.get("title"), str):
            record["title"] = _repair_mojibake(record["title"])
        if isinstance(record.get("text"), str):
            record["text"] = _repair_mojibake(record["text"])
    index["index_version"] = INDEX_VERSION
    index["chat_model"] = choose_chat_model()
    index.setdefault("indexed_at", time.time())
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


def _index_needs_migration(index: dict[str, Any]) -> bool:
    if index.get("index_version") != INDEX_VERSION:
        return True
    for record in index.get("records", []):
        text = record.get("text", "")
        if isinstance(text, str) and any(marker in text for marker in MOJIBAKE_MARKERS):
            return True
    return False


def _clean_text(text: str) -> str:
    text = _repair_mojibake(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _chunk_plain_text(path: Path, text: str) -> list[RagChunk]:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    kind = "documentation" if path.suffix.lower() == ".md" else "code"
    paragraphs = []
    for paragraph in [p.strip() for p in re.split(r"\n\s*\n", _clean_text(text)) if p.strip()]:
        if len(paragraph) <= MAX_TEXT_CHARS:
            paragraphs.append(paragraph)
        else:
            for start in range(0, len(paragraph), MAX_TEXT_CHARS):
                paragraphs.append(paragraph[start : start + MAX_TEXT_CHARS])
    chunks: list[RagChunk] = []
    current = ""
    idx = 1
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 > MAX_TEXT_CHARS and current:
            chunks.append(_make_chunk(rel, path.name, kind, current, idx))
            idx += 1
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(_make_chunk(rel, path.name, kind, current, idx))
    return chunks


def _chunk_csv(path: Path) -> list[RagChunk]:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return _chunk_plain_text(path, _read_text(path))

    chunks: list[RagChunk] = []
    summary = [
        f"Dataset: {rel}",
        f"Rows: {len(df)}",
        f"Columns: {', '.join(map(str, df.columns.tolist()))}",
    ]
    for col in df.columns[:12]:
        series = df[col]
        if series.dtype == object:
            values = series.dropna().astype(str).str.strip()
            top = values[values != ""].value_counts().head(8)
            if not top.empty:
                summary.append(f"Top values for {col}: " + ", ".join(f"{k}={v}" for k, v in top.items()))
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().any():
                summary.append(
                    f"{col}: min={numeric.min():.2f}, mean={numeric.mean():.2f}, max={numeric.max():.2f}"
                )
    chunks.append(_make_chunk(rel, path.name, "dataset", "\n".join(summary), 1))

    row_group = 20 if len(df) > 200 else 12
    for start in range(0, len(df), row_group):
        group = df.iloc[start : start + row_group]
        records = group.fillna("").to_dict(orient="records")
        text = f"Dataset rows from {rel}, rows {start + 1}-{start + len(group)}:\n"
        text += json.dumps(records, ensure_ascii=False, indent=2)
        chunks.append(_make_chunk(rel, path.name, "dataset", text[:MAX_TEXT_CHARS], len(chunks) + 1))
    return chunks


def _chunk_json(path: Path) -> list[RagChunk]:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        raw = json.loads(_read_text(path))
    except Exception:
        return _chunk_plain_text(path, _read_text(path))

    if isinstance(raw, dict) and "features" in raw and isinstance(raw["features"], list):
        chunks = [
            _make_chunk(
                rel,
                path.name,
                "geojson",
                f"GeoJSON export {rel}: {len(raw['features'])} features. Properties include medical facility names, categories, districts, confidence, and coordinates.",
                1,
            )
        ]
        for start in range(0, len(raw["features"]), 25):
            sample = raw["features"][start : start + 25]
            text = f"GeoJSON features from {rel}, rows {start + 1}-{start + len(sample)}:\n"
            text += json.dumps(sample, ensure_ascii=False)[:MAX_TEXT_CHARS]
            chunks.append(_make_chunk(rel, path.name, "geojson", text, len(chunks) + 1))
        return chunks

    text = json.dumps(raw, ensure_ascii=False, indent=2)
    return _chunk_plain_text(path, text)


def _make_chunk(rel: str, title: str, kind: str, text: str, idx: int) -> RagChunk:
    text = _repair_mojibake(text).strip()
    digest = hashlib.sha1(f"{rel}:{idx}:{text[:100]}".encode("utf-8")).hexdigest()[:16]
    return RagChunk(
        id=digest,
        title=f"{title} #{idx}",
        source_path=rel,
        kind=kind,
        text=text,
    )


def collect_chunks() -> list[RagChunk]:
    chunks: list[RagChunk] = []
    for path in _project_files():
        suffix = path.suffix.lower()
        if suffix == ".csv":
            chunks.extend(_chunk_csv(path))
        elif suffix in {".json", ".geojson"}:
            chunks.extend(_chunk_json(path))
        else:
            chunks.extend(_chunk_plain_text(path, _read_text(path)))
    return chunks


def _chunks_for_path(path: Path) -> list[RagChunk]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _chunk_csv(path)
    if suffix in {".json", ".geojson"}:
        return _chunk_json(path)
    return _chunk_plain_text(path, _read_text(path))


def _path_priority(path: Path) -> tuple[int, str]:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    if rel in {"README.md", "invest_search_medical_casablanca_research.md"}:
        return (0, rel)
    if rel.startswith("docs/"):
        return (1, rel)
    if rel.startswith("data/processed/zone_profiles/"):
        return (2, rel)
    if rel.startswith("data/processed/"):
        return (3, rel)
    if rel.startswith("data/exports/"):
        return (4, rel)
    if rel.startswith("data/manual/") or rel.endswith("casablanca_districts.csv"):
        return (5, rel)
    if rel.startswith(("app/utils/", "data_sources/", "scripts/")):
        return (6, rel)
    if rel.startswith(("app/", "api/")):
        return (7, rel)
    return (9, rel)


def _priority(chunk: RagChunk) -> tuple[int, str]:
    path = chunk.source_path
    if path in {"README.md", "invest_search_medical_casablanca_research.md"}:
        return (0, path)
    if path.startswith("docs/"):
        return (1, path)
    if path.startswith("data/processed/zone_profiles/"):
        return (2, path)
    if path.startswith("data/processed/"):
        return (3, path)
    if path.startswith("data/exports/"):
        return (4, path)
    if path.startswith("data/manual/") or path.endswith("casablanca_districts.csv"):
        return (5, path)
    if path.startswith("app/utils/") or path.startswith("data_sources/") or path.startswith("scripts/"):
        return (6, path)
    if path.startswith("app/") or path.startswith("api/"):
        return (7, path)
    return (9, path)


def priority_chunks(max_chunks: int | None = DEFAULT_MAX_CHUNKS) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    for path in sorted(_project_files(), key=_path_priority):
        chunks.extend(_chunks_for_path(path))
        if max_chunks and max_chunks > 0 and len(chunks) >= max_chunks:
            return chunks[:max_chunks]
    return chunks


def embed_text(text: str) -> list[float]:
    payload = {"model": EMBED_MODEL, "prompt": text}
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings", json=payload, timeout=EMBED_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()["embedding"]


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
            timeout=EMBED_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings")
        if embeddings and len(embeddings) == len(texts):
            return embeddings
    except requests.HTTPError as exc:
        # Older Ollama versions may not expose the batch endpoint.
        if exc.response is None or exc.response.status_code != 404:
            raise
        return [embed_text(text) for text in texts]
    except requests.RequestException:
        raise
    raise RuntimeError("Ollama returned an incomplete embedding batch")


def build_index(force: bool = False) -> dict[str, Any]:
    global _index_cache, _index_mtime
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_PATH.exists() and not force:
        return load_index()

    chunks = priority_chunks()
    existing_embeddings: dict[str, list[float]] = {}
    if INDEX_PATH.exists():
        try:
            old = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            for rec in old.get("records", []):
                if rec.get("embedding"):
                    existing_embeddings[rec["id"]] = rec["embedding"]
        except Exception:
            pass

    records = []
    to_embed: list[tuple[int, str]] = []
    for i, chunk in enumerate(chunks):
        if chunk.id in existing_embeddings:
            chunk.embedding = existing_embeddings[chunk.id]
        else:
            to_embed.append((i, f"{chunk.title}\nSource: {chunk.source_path}\n\n{chunk.text[:MAX_TEXT_CHARS]}"))

    embedding_available = not SKIP_EMBEDDINGS and _ollama_available()
    if to_embed and embedding_available:
        batch_size = int(os.environ.get("RAG_EMBED_BATCH_SIZE", "8"))
        texts = [t for _, t in to_embed]
        embeddings: list[list[float]] = [[] for _ in texts]
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            try:
                batch_embeddings = embed_batch(batch)
            except Exception:
                break
            embeddings[start : start + len(batch_embeddings)] = batch_embeddings
        for (idx, _), emb in zip(to_embed, embeddings):
            if emb:
                chunks[idx].embedding = emb

    for chunk in chunks:
        records.append(chunk.__dict__)

    embedded_count = sum(bool(record.get("embedding")) for record in records)
    embedding_status = (
        "complete" if embedded_count == len(records)
        else "partial" if embedded_count
        else "lexical_only"
    )
    index = {
        "index_version": INDEX_VERSION,
        "embedding_model": EMBED_MODEL,
        "chat_model": choose_chat_model(),
        "chunk_count": len(records),
        "embedding_status": embedding_status,
        "embedded_count": embedded_count,
        "indexed_at": time.time(),
        "records": records,
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    _index_cache = index
    _index_mtime = INDEX_PATH.stat().st_mtime
    return index


def load_index() -> dict[str, Any]:
    global _index_cache, _index_mtime
    if not INDEX_PATH.exists():
        return build_index(force=True)
    mt = INDEX_PATH.stat().st_mtime
    if _index_cache is not None and mt == _index_mtime:
        return _index_cache
    loaded = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if _index_needs_migration(loaded):
        loaded = _migrate_index(loaded)
        mt = INDEX_PATH.stat().st_mtime
    _index_cache = loaded
    _index_mtime = mt
    return _index_cache


def _ollama_available() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


def semantic_search(query: str, top_k: int = 8) -> list[dict[str, Any]]:
    index = load_index()
    records = index.get("records", [])
    if not records:
        return []

    q = np.array(embed_text(query), dtype=np.float32)
    q_norm = float(np.linalg.norm(q)) or 1.0
    scored = []
    for record in records:
        emb = record.get("embedding")
        if not emb:
            continue
        emb_arr = np.array(emb, dtype=np.float32)
        denom = q_norm * (float(np.linalg.norm(emb_arr)) or 1.0)
        score = float(np.dot(q, emb_arr) / denom)
        scored.append({**record, "score": round(score, 4)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _tokenize(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.findall(r"[0-9a-z]{2,}", folded)


def _source_alias_text(source_path: str) -> str:
    """Small metadata aliases for tabular sources whose filenames carry intent."""
    source = source_path.replace("\\", "/").lower()
    aliases: list[str] = []
    if "medical_facilities_clean" in source:
        aliases.append(
            "liste etablissements medicaux pharmacies cliniques hopitaux cabinets "
            "dentistes veterinaires laboratoires radiologie nettoyes clean csv points sante geocodes"
        )
    if "docs/methodology.md" in source:
        aliases.append(
            "methodologie methode calcul score scoring opportunite investissement moteur "
            "formule indicateurs supply gap risque concurrence fiabilite"
        )
    if "docs/data_dictionary.md" in source:
        aliases.append(
            "dictionnaire donnees colonnes schema champs variables area indicators "
            "definitions dataset fichiers csv"
        )
    if "docs/sources.md" in source:
        aliases.append("sources donnees openstreetmap osm hcp ministere sante licences provenance")
    if "area_indicators" in source:
        aliases.append("population densite quartiers arrondissements zones indicateurs menages")
    if "specialty_supply" in source:
        aliases.append("offre specialite concurrence prestataires supply gap medical sante")
    if "sector_supply" in source:
        aliases.append("secteur sector supply gap concurrence restauration commerce education wellness")
    if "subcategory_supply" in source:
        aliases.append("activite subcategory categorie cafes restaurants supermarches ecoles sport")
    return " ".join(aliases)


def _is_metadata_query(query: str) -> bool:
    tokens = set(_tokenize(query))
    metadata_tokens = {
        "comment",
        "fonctionne",
        "methodologie",
        "methodologie",
        "methode",
        "scoring",
        "score",
        "sources",
        "source",
        "donnees",
        "dictionnaire",
        "colonnes",
        "fichier",
        "dataset",
        "csv",
        "liste",
        "nettoyes",
        "nettoyees",
    }
    return bool(tokens & metadata_tokens)


def lexical_search(query: str, top_k: int = 8) -> list[dict[str, Any]]:
    index = load_index()
    records = index.get("records", [])
    if not records:
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    doc_freq: Counter[str] = Counter()
    doc_tokens: list[Counter[str]] = []
    for rec in records:
        # Include source metadata in the lexical field so queries that ask for a
        # specific dataset/file (for example "medical facilities clean csv") can
        # recover the right evidence even when the chunk text is mostly tabular.
        lexical_field = " ".join(
            [
                rec.get("text", ""),
                rec.get("title", ""),
                rec.get("source_path", ""),
                _source_alias_text(rec.get("source_path", "")),
                rec.get("kind", ""),
            ]
        )
        tokens = Counter(_tokenize(lexical_field))
        doc_tokens.append(tokens)
        for t in set(tokens):
            doc_freq[t] += 1

    n = len(records)
    scored = []
    for i, rec in enumerate(records):
        tf = doc_tokens[i]
        bm25 = 0.0
        doc_len = sum(tf.values()) or 1
        k1, b = 1.5, 0.75
        avg_dl = sum(sum(d.values()) for d in doc_tokens) / n if n else 1
        for qt in query_tokens:
            if qt not in tf:
                continue
            idf = math.log((n - doc_freq[qt] + 0.5) / (doc_freq[qt] + 0.5) + 1.0)
            tf_val = tf[qt]
            bm25 += idf * (tf_val * (k1 + 1)) / (tf_val + k1 * (1 - b + b * doc_len / avg_dl))
        if bm25 > 0:
            norm_score = round(min(1.0, bm25 / 15.0), 4)
            scored.append({**rec, "score": norm_score})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _reciprocal_rank_fusion(
    rankings: list[list[dict[str, Any]]], top_k: int
) -> list[dict[str, Any]]:
    """Fuse several ranked result lists with Reciprocal Rank Fusion.

    RRF is rank-based, so it sidesteps the fact that cosine similarity and BM25
    live on different scales. Each document's fused weight is the sum over rankers
    of 1 / (RRF_K + rank). We keep the original per-ranker scores on the record so
    the UI can still show a meaningful similarity (prefer the semantic cosine,
    fall back to lexical) instead of the tiny RRF weight.
    """
    fused_weight: dict[str, float] = {}
    merged: dict[str, dict[str, Any]] = {}

    for ranking in rankings:
        for rank, record in enumerate(ranking):
            rid = record["id"]
            fused_weight[rid] = fused_weight.get(rid, 0.0) + 1.0 / (RRF_K + rank + 1)
            if rid not in merged:
                merged[rid] = dict(record)
            # Preserve each signal's score under an explicit key.
            score_key = "semantic_score" if record.get("_ranker") == "semantic" else "lexical_score"
            merged[rid][score_key] = record.get("score", 0.0)

    results: list[dict[str, Any]] = []
    for rid, weight in fused_weight.items():
        record = merged[rid]
        # Display/confidence score: real similarity beats raw fusion weight.
        display = record.get("semantic_score", record.get("lexical_score", 0.0))
        record["rrf_weight"] = round(weight, 6)
        record["score"] = round(float(display), 4)
        record.pop("_ranker", None)
        results.append(record)

    results.sort(key=lambda item: (item["rrf_weight"], item["score"]), reverse=True)
    return results[:top_k]


def cap_per_source(
    results: list[dict[str, Any]], top_k: int, max_per_source: int = MAX_PER_SOURCE
) -> list[dict[str, Any]]:
    """Limit how many chunks from one source file appear in the top_k.

    Walks the ranked list keeping the best `max_per_source` chunks per file;
    overflow chunks are only used to backfill if there aren't enough distinct
    sources to fill top_k. Preserves ranking order otherwise.
    """
    if max_per_source <= 0:
        return results[:top_k]
    seen: Counter[str] = Counter()
    kept: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    for record in results:
        source = record.get("source_path", "")
        if seen[source] < max_per_source:
            kept.append(record)
            seen[source] += 1
        else:
            overflow.append(record)
        if len(kept) >= top_k:
            break
    for record in overflow:
        if len(kept) >= top_k:
            break
        kept.append(record)
    return kept[:top_k]


def hybrid_search(query: str, top_k: int = 8) -> tuple[list[dict[str, Any]], str]:
    """Retrieve top_k chunks, fusing semantic + lexical signals when possible.

    Modes (RAG_HYBRID_MODE): "rrf" fuses both rankers (default), "semantic" or
    "lexical" force a single ranker. Falls back gracefully when Ollama embeddings
    are unavailable. A per-source diversity cap is applied to the final list.
    """
    candidate_k = max(top_k, top_k * CANDIDATE_MULTIPLIER)

    semantic_results: list[dict[str, Any]] = []
    if HYBRID_MODE in ("rrf", "semantic"):
        try:
            if _ollama_available():
                semantic_results = semantic_search(query, top_k=candidate_k)
                for rec in semantic_results:
                    rec["_ranker"] = "semantic"
        except Exception:
            semantic_results = []

    lexical_results: list[dict[str, Any]] = []
    if HYBRID_MODE in ("rrf", "lexical") or not semantic_results:
        lexical_results = lexical_search(query, top_k=candidate_k)
        for rec in lexical_results:
            rec["_ranker"] = "lexical"

    # Resolve the ranked list and a mode label, before diversity capping.
    if HYBRID_MODE == "semantic" and semantic_results:
        ranked, mode = semantic_results, "semantic"
    elif HYBRID_MODE == "lexical":
        ranked, mode = lexical_results, "lexical"
    elif semantic_results and lexical_results and _is_metadata_query(query):
        ranked, mode = lexical_results, "lexical_metadata"
    elif semantic_results and lexical_results:
        ranked = _reciprocal_rank_fusion(
            [semantic_results, lexical_results], len(semantic_results) + len(lexical_results)
        )
        mode = "hybrid"
    elif semantic_results:
        ranked, mode = semantic_results, "semantic"
    else:
        ranked, mode = lexical_results, "lexical"

    for rec in ranked:
        rec.pop("_ranker", None)
    return cap_per_source(ranked, top_k), mode


def generate_with_ollama(question: str, scoring_context: str, contexts: list[dict[str, Any]]) -> str:
    model = choose_chat_model()
    context_text = "\n\n".join(
        f"[{i + 1}] {ctx['title']} | {ctx['source_path']} | score={ctx['score']}\n{ctx['text'][:CHAT_CONTEXT_CHARS]}"
        for i, ctx in enumerate(contexts[:CHAT_CONTEXT_LIMIT])
    )
    system = (
        "Tu es Invest Search Intelligence, un analyste d'implantation a Casablanca (sante, restauration, "
        "commerce, education, bien-etre). "
        "Reponds en francais clair, avec un style Perplexity: synthese courte, points KPI, risques, et sources. "
        "Utilise uniquement les donnees et contextes fournis. Si une donnee est incertaine, dis-le. "
        "Refuse les demandes hors perimetre: ouvrir un site web, piloter le navigateur, divertissement, "
        "sport, people, insultes, programmation ou tout sujet sans lien avec l'analyse d'implantation a Casablanca. "
        "Dans ce cas, reponds seulement que la demande est hors perimetre Invest Search, sans score ni recommandation. "
        "Ne donne pas de conseil financier/legal definitif; recommande une validation terrain."
    )
    prompt = (
        f"QUESTION UTILISATEUR:\n{question}\n\n"
        f"CONTEXTE SCORE / OUTILS:\n{scoring_context}\n\n"
        f"CONTEXTES RECUPERES PAR RECHERCHE SEMANTIQUE:\n{context_text}\n\n"
        "Redige une reponse structuree en markdown. Inclure: recommandation principale, 3-5 KPIs, "
        "risques/limites de donnees, et une ligne 'Sources utilisees'."
    )
    if "qwen3" in model.lower():
        prompt += "\n/no_think"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 2048,
            "num_predict": 220,
        },
    }
    response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=CHAT_TIMEOUT_SECONDS)
    response.raise_for_status()
    content = response.json()["message"]["content"]
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def source_cards_from_contexts(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards = []
    seen = set()
    for ctx in contexts:
        source = ctx["source_path"]
        if source in seen:
            continue
        seen.add(source)
        cards.append(
            {
                "title": source.split("/")[-1],
                "subtitle": source,
                "kind": ctx.get("kind", "documentation"),
                "metric": f"{ctx['score']:.2f}",
                "confidence": max(0.4, min(1.0, float(ctx["score"]))),
            }
        )
        if len(cards) == 5:
            break
    return cards


def rag_status() -> dict[str, Any]:
    installed = _ollama_models()
    index_exists = INDEX_PATH.exists()
    chunk_count = 0
    indexed_at = None
    embedding_status = "missing"
    embedded_count = 0
    if index_exists:
        try:
            idx = load_index()
            chunk_count = idx.get("chunk_count", 0)
            indexed_at = idx.get("indexed_at")
            embedding_status = idx.get("embedding_status", "unknown")
            embedded_count = idx.get("embedded_count", 0)
        except Exception:
            chunk_count = 0
    return {
        "ollama_url": OLLAMA_URL,
        "ollama_available": _ollama_available(),
        "installed_models": installed,
        "chat_model": choose_chat_model(),
        "embedding_model": EMBED_MODEL,
        "index_exists": index_exists,
        "chunk_count": chunk_count,
        "embedded_count": embedded_count,
        "embedding_status": embedding_status,
        "active_retrieval": "hybrid" if _ollama_available() else "lexical",
        "indexed_at": indexed_at,
    }
