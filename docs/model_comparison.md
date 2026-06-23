# Model & Retrieval Accuracy Comparison — Invest Search RAG

This report answers two questions with measurements, not opinion:

1. **Which chat model is more accurate/precise — `qwen3:8b` or `qwen2.5:7b`?**
   (Your request said "qwen 3.5 vs qwen 2"; see the note below on what those
   names actually resolve to.)
2. **Which retrieval strategy is better — semantic, lexical, or hybrid?**

Everything here is reproducible:

```
python scripts/ab_eval_models.py        # model A/B  -> artifacts/ab_model_eval.json
python scripts/evaluate_retrieval.py     # retrieval  -> artifacts/retrieval_eval.json
```

---

## 0. Important correction on model names

The code's model preference list was topped by **`qwen3.6` and `qwen3.5` — tags
Alibaba never released** and that were not installed, so selection silently fell
through to the real installed model, `qwen3:latest` (8.2B). The only "qwen 2"
present was `qwen2.5:0.5b` (494M), which the code **deliberately skips** as too
small. So the meaningful comparison is **`qwen3:8b` vs `qwen2.5:7b`** (a fair
size match). The phantom entries have been removed and selection unified in
`api/services/llm/model_select.py`.

---

## 1. Model A/B — method

For each model, on 7 in-scope investment questions (no explicit zone, so they
reach the LLM rather than the deterministic path), we pin the model, build the
**identical** scoring context + retrieved contexts, and score the **raw** model
answer (isolated from the app's deterministic merge) on a 0–100 rubric:

| Criterion | Pts | Checks |
|---|---:|---|
| grounded_zone | 25 | names the zone the scoring engine recommended |
| numbers_grounded | 15 | share of substantive numbers that trace to the data |
| has_citation | 15 | uses `[n]` / "Source" |
| no_foreign_zone | 10 | doesn't present a *different* district as the rec |
| has_risk | 10 | includes risks / limits |
| has_next_steps | 9 | includes field-validation steps |
| has_population | 8 | cites population |
| has_density | 8 | cites density |

Refusing an in-scope question multiplies the score by 0.3 (hard failure).

---

## 2. Model A/B — results

### Run 1 (as-shipped, `num_predict=150`)

| model | composite | grounded_zone | no_foreign | citation | risk | numbers_grounded | latency (s) | words |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen3:8b   | 77.5 | 1.00 | 1.00 | 1.00 | 0.00 | 0.84 | ~5 | 69 |
| qwen2.5:7b | 77.6 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | ~5 | 74 |

**Two findings from run 1:**

- The models are **statistically tied** (77.5 vs 77.6). The only separator is
  **number faithfulness**: `qwen2.5:7b` grounded 100% of its numbers, `qwen3:8b`
  occasionally emitted a figure not present in the data (0.84). For an investment
  tool, not inventing numbers is the most valuable property.
- **`has_risk = 0.00` for *both* models** — not because they're bad, but because
  `num_predict=150` truncated every answer after the recommendation/rationale,
  before the risks and next-steps sections could render. This is a config bug,
  fixed below.

### Run 2 (after fix, `num_predict=400`)

Raising the token budget let the full 6-section note render — `has_risk` went
from 0.00 → **1.00 for both models**, and composite scores jumped ~20 points.
(One rubric refinement between runs: a *genuine* refusal is now defined as short
**and** lacking a recommendation, so a complete answer that merely echoes the
system prompt's "hors périmètre" scope language is no longer mis-flagged.)

| model | composite | grounded_zone | no_foreign | citation | risk | numbers_grounded | latency (s) | words |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **qwen3:8b**   | **98.5** | 1.00 | 1.00 | 1.00 | 1.00 | 0.90 | 14.7 | 179 |
| qwen2.5:7b | 96.1 | 1.00 | 1.00 | 1.00 | 1.00 | **0.97** | **12.5** | 173 |

**The trade-off, precisely (per-question breakdown):**

- **`qwen3:8b` — more complete.** Included every section (incl. the density KPI)
  on all 7 questions. Its only weakness: on 2 questions it emitted some numbers
  not present in the data (number-grounding dropped to 0.64 / 0.67) — i.e. mild
  numeric hallucination.
- **`qwen2.5:7b` — more faithful and faster.** Its numbers were almost always
  grounded (0.97 overall), and it ran ~15% faster. Its weakness: it omitted the
  **density** KPI on 3 of 7 questions.

So the verdict depends on what you weight. For an investment tool, **fabricated
numbers are the worst failure mode**, which favours `qwen2.5:7b`; if you value a
guaranteed-complete structure, `qwen3:8b` edges ahead on the composite. Both are
strong (96–98) once the token budget is fixed — the model is **not** the
accuracy bottleneck.

---

## 3. Retrieval — semantic vs lexical vs hybrid

Method: 10 labeled `query → expected source file` pairs; metrics at the source
file level (Precision@5, Recall@5, Hit@5, MRR). Each strategy uses the same
per-source diversity cap so the comparison is fair.

### Before vs after the retrieval fixes

The original `hybrid_search` was *"semantic OR lexical"* (semantic only if its
top cosine > 0.3, else fall back entirely to lexical) and applied **no source
diversity**, so one verbose document monopolised the top-k.

| config | Hit@5 (hybrid) | MRR (hybrid) |
|---|---:|---:|
| original (no diversity cap) | 0.20 | 0.12 |
| + per-source cap = 2 | 0.60 | 0.218 |
| **+ per-source cap = 1 (shipped)** | **0.90** | **0.328** |

### Final per-strategy (cap=1, RRF)

| mode | P@5 | Recall@5 | Hit@5 | MRR |
|---|---:|---:|---:|---:|
| semantic | 0.16 | 0.70 | 0.80 | 0.303 |
| lexical | 0.12 | 0.55 | 0.60 | 0.267 |
| **hybrid (RRF)** | **0.18** | **0.80** | **0.90** | **0.328** |

**Findings:**

- The **biggest retrieval win was source diversity**, not the model: capping
  chunks-per-source lifted Hit@5 from 0.20 → 0.90.
- With that fix, **true hybrid (Reciprocal Rank Fusion) beats both single
  rankers** on every metric — fusion genuinely helps.
- On this French corpus, **lexical BM25 alone slightly beats pure semantic**
  (`nomic-embed-text` is weak on French). This argues for (a) keeping the hybrid
  fuser and (b) a future embedding-model upgrade (e.g. `bge-m3`) as the next
  retrieval lever.

---

## 4. Recommendation

- **Chat model:** both score 96–98 once `num_predict` is fixed — the model is not
  the bottleneck. Pick on your priority:
  - Prefer **`qwen2.5:7b`** (`OLLAMA_CHAT_MODEL=qwen2.5:7b`) if you weight
    *number-faithfulness* (0.97 vs 0.90) and *speed* (~15% faster) most — the
    safest choice for an investment tool, and the direction you asked for.
  - Prefer **`qwen3:8b`** if you weight *structural completeness* (it never
    dropped a KPI; qwen2.5:7b occasionally omits density) — it takes the top
    composite (98.5).
  - Either way, a one-line KPI check in the app (already present:
    `build_rag_answer` appends the deterministic KPI block when the LLM omits
    population/density) covers qwen2.5:7b's density gap, making it a strong
    default.
- **Retrieval:** ship **hybrid RRF + per-source cap = 1** (done). Biggest next
  lever is a stronger multilingual embedding model, then richer indexable data
  (see `docs/data_enrichment_study.md`).
- **Generation:** keep `num_predict ≥ 400` so the full investment note renders.

> Net: the accuracy gains here came less from swapping the LLM and more from
> **fixing retrieval diversity and the generation token budget** — both measured,
> both reversible via env vars.
