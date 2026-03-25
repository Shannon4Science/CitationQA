"""
Earth-Agent real citation-evaluation smoke test.

Runs a small real sample and reports how many citations are resolved through
LLM search directly, after fetch-assisted search, or via fallback.
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.modules.fulltext_fetcher import FulltextFetcher
from backend.modules.llm_evaluator import LLMEvaluator
from backend.modules.paper_search import UnifiedPaperSearch


TARGET_TITLE = "Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents"


def _candidate_links(citation):
    links = []
    arxiv_id = citation.get("arxiv_id") or citation.get("externalIds", {}).get("ArXiv")
    if arxiv_id:
        links.extend([
            f"https://arxiv.org/abs/{arxiv_id}",
            f"https://arxiv.org/pdf/{arxiv_id}",
            f"https://arxiv.org/html/{arxiv_id}",
        ])
    if citation.get("doi"):
        links.append(f"https://doi.org/{citation['doi']}")
    if citation.get("open_access_pdf"):
        links.append(citation["open_access_pdf"])
    return [link for link in links if link]


def evaluate_one(evaluator, target_paper, citation):
    title = citation.get("title", "")
    extra_links = _candidate_links(citation)

    first = evaluator.evaluate_single_citation(
        target_paper, citation, "", "search_only",
        None, extra_links or None, "", True, True
    )
    if isinstance(first, dict) and first.get("evaluation_method") == "web_search":
        return {
            "title": title,
            "method": "web_search",
            "search_stage": "first_pass",
            "content_type": "search_only",
            "quality_score": first.get("quality_score", 0),
            "sources": len(first.get("evidence_sources", [])),
        }

    fetcher = FulltextFetcher()
    try:
        ctx = fetcher.fetch_fulltext_with_citation_context(citation, target_paper.get("title", ""))
    finally:
        fetcher.close()

    fulltext = ctx.get("fulltext") or citation.get("abstract", "")
    annotated = ctx.get("annotated_content") or fulltext
    content_type = ctx.get("content_type", "none")
    citation_contexts = ctx.get("citation_contexts", [])
    source_url = ctx.get("fulltext_url")

    fulltext_links = list(extra_links)
    if source_url:
        fulltext_links.append(source_url)

    second = evaluator.evaluate_single_citation(
        target_paper, citation, "", content_type,
        citation_contexts if citation_contexts else None,
        fulltext_links or None,
        annotated[:2200], True, True
    )
    if isinstance(second, dict) and second.get("evaluation_method") == "web_search":
        return {
            "title": title,
            "method": "web_search",
            "search_stage": "second_pass",
            "content_type": content_type,
            "quality_score": second.get("quality_score", 0),
            "sources": len(second.get("evidence_sources", [])),
            "citation_contexts": len(citation_contexts),
        }

    fallback = evaluator.evaluate_single_citation(
        target_paper, citation, annotated, content_type,
        citation_contexts if citation_contexts else None,
        fulltext_links or None,
        annotated[:2200], False, False
    )
    return {
        "title": title,
        "method": fallback.get("evaluation_method", "unknown"),
        "search_stage": "fallback",
        "content_type": content_type,
        "quality_score": fallback.get("quality_score", 0),
        "citation_contexts": len(citation_contexts),
        "first_status": first.get("status") if isinstance(first, dict) else "none",
        "second_status": second.get("status") if isinstance(second, dict) else "none",
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    limit = int(os.environ.get("EARTH_AGENT_LIMIT", "8"))
    search = UnifiedPaperSearch()
    try:
        target_paper = search.search_paper(TARGET_TITLE)
        if not target_paper:
            raise RuntimeError("Target paper not found")
        citations = search.get_citations(target_paper, limit=limit)
    finally:
        search.close()

    evaluator = LLMEvaluator()
    results = []
    for idx, citation in enumerate(citations[:limit], start=1):
        print(f"[{idx}/{min(len(citations), limit)}] evaluating: {citation.get('title', '')[:90]}")
        results.append(evaluate_one(evaluator, target_paper, citation))

    first_pass = sum(1 for item in results if item.get("search_stage") == "first_pass")
    second_pass = sum(1 for item in results if item.get("search_stage") == "second_pass")
    fallback = sum(1 for item in results if item.get("search_stage") == "fallback")
    payload = {
        "target_title": TARGET_TITLE,
        "sample_size": len(results),
        "first_pass_search_success": first_pass,
        "second_pass_search_success": second_pass,
        "fallback_count": fallback,
        "search_success_rate": round(100.0 * (first_pass + second_pass) / max(len(results), 1), 2),
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
