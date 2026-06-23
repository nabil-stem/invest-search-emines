"""Free web-search fallback (DuckDuckGo HTML endpoint, no API key).

Used only when the user explicitly presses "Recherche Web". Results are NOT
grounded in our datasets — they come from the open web and are clearly labelled
as unverified. Always best-effort: any network/parse failure returns [].

No paid API, no extra dependency: we POST to html.duckduckgo.com and parse the
result list with BeautifulSoup (already a dependency).
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_ENDPOINT = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
}


def _clean_url(href: str) -> str:
    """DuckDuckGo wraps result links in a /l/?uddg=... redirect — unwrap it."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        if "uddg" in params:
            return unquote(params["uddg"][0])
    return href


def search_web(query: str, max_results: int = 5, timeout: float = 6.0) -> list[dict]:
    """Return up to ``max_results`` web results: {title, url, snippet}. [] on failure."""
    q = (query or "").strip()
    if not q:
        return []
    # Bias toward local relevance when the query doesn't already name the geography.
    low = q.lower()
    if "casa" not in low and "maroc" not in low and "morocco" not in low:
        q = f"{q} Casablanca Maroc"
    try:
        resp = requests.post(
            _ENDPOINT, data={"q": q, "kl": "fr-fr"}, headers=_HEADERS, timeout=timeout
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - best-effort fallback
        logger.info("web search failed: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []
    seen: set[str] = set()
    for node in soup.select(".result"):
        link = node.select_one(".result__a")
        if not link:
            continue
        url = _clean_url(link.get("href", ""))
        title = link.get_text(" ", strip=True)
        if not url or not title or url in seen:
            continue
        snippet_el = node.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        results.append({"title": title, "url": url, "snippet": snippet})
        seen.add(url)
        if len(results) >= max_results:
            break
    return results


def format_web_section(results: list[dict]) -> str:
    """Render web results as a clearly-labelled, unverified markdown section."""
    if not results:
        return (
            "\n\n## Recherche web\n\n"
            "*Aucun résultat web exploitable pour cette requête "
            "(ou le service est momentanément indisponible).*"
        )
    lines = ["\n\n## Recherche web — sources externes (non vérifiées)\n"]
    for r in results:
        snippet = f" — {r['snippet']}" if r.get("snippet") else ""
        lines.append(f"- [{r['title']}]({r['url']}){snippet}")
    lines.append(
        "\n> ⚠️ Résultats issus du web ouvert, **hors de nos jeux de données** "
        "(HCP, OSM, Min. Santé). À recouper avant toute décision."
    )
    return "\n".join(lines)
