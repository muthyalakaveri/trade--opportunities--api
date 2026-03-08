# search.py
# Handles: Web search using DuckDuckGo to get current sector news/data

import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# MAIN SEARCH FUNCTION
# ─────────────────────────────────────────
def search_sector_data(sector: str, max_results: int = 3) -> list[dict]:
    """
    Searches DuckDuckGo for current market news about an Indian sector.

    Args:
        sector: e.g. "pharmaceuticals", "technology", "agriculture"
        max_results: number of results to fetch

    Returns:
        List of dicts with keys: title, href, body
    """
    queries = [
        f"India {sector} sector trade opportunities 2024 2025",
        f"India {sector} export import market trends",
        f"India {sector} industry growth challenges",
    ]

    all_results = []

    with DDGS() as ddgs:
        for query in queries:
            try:
                results = list(ddgs.text(query, max_results=max_results // 3 + 1))
                all_results.extend(results)
                logger.info(f"Search query '{query}' returned {len(results)} results")
            except Exception as e:
                logger.warning(f"Search failed for query '{query}': {e}")
                continue

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r.get("href", "")
        if url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    logger.info(f"Total unique search results for '{sector}': {len(unique_results)}")
    return unique_results[:max_results]


# ─────────────────────────────────────────
# FORMAT RESULTS FOR AI PROMPT
# ─────────────────────────────────────────
def format_results_for_prompt(results: list[dict]) -> str:
    """
    Converts search results into a clean text block
    that can be passed to the Gemini API prompt.
    """
    if not results:
        return "No search results found. Please rely on your training knowledge."

    formatted = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        body = r.get("body", "No description")
        url = r.get("href", "")
        formatted.append(f"[{i}] {title}\n{body}\nSource: {url}")

    return "\n\n".join(formatted)
