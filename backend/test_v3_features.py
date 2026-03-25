import json
import logging
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.modules.fulltext_fetcher import FulltextFetcher
from backend.modules.paper_search import UnifiedPaperSearch


def test_pdf_discovery():
    fetcher = FulltextFetcher()
    cases = [
        {
            "title": "CausalGame: Benchmarking Causal Thinking of LLM Agents in Games",
            "url": "https://openreview.net/forum?id=SEFSkn4l6d",
            "expected_pdf_url": "https://openreview.net/pdf?id=SEFSkn4l6d",
        },
        {
            "title": "A Comprehensive Survey of Agentic AI for Spatio-Temporal Data",
            "url": "https://www.preprints.org/manuscript/202601.2236",
            "expected_pdf_url": "https://www.preprints.org/manuscript/202601.2236/v1/download",
        },
    ]

    results = []
    for case in cases:
        html = fetcher._fetch_page_html(case["url"])
        site_candidates = fetcher._site_specific_pdf_candidates(case["url"], html)
        html_candidates = fetcher._extract_pdf_urls_from_html(case["url"], html) if html else []
        all_candidates = fetcher._dedupe_urls(site_candidates + html_candidates)
        try:
            expected_resp = fetcher._http_get(case["expected_pdf_url"], accept="application/pdf,*/*")
            expected_status = expected_resp.status_code
            expected_pdf = expected_resp.content[:5] == b"%PDF-" or "application/pdf" in expected_resp.headers.get("content-type", "").lower()
        except Exception as exc:
            expected_status = f"error: {exc}"
            expected_pdf = False
        results.append(
            {
                "url": case["url"],
                "expected_pdf_url": case["expected_pdf_url"],
                "html_fetched": bool(html),
                "site_candidates": site_candidates[:10],
                "html_candidates": html_candidates[:10],
                "matched_expected": case["expected_pdf_url"] in all_candidates,
                "expected_url_status": expected_status,
                "expected_url_is_pdf": expected_pdf,
            }
        )

    fetcher.close()
    return results


def test_influence_scoring():
    search = UnifiedPaperSearch()

    target = search.search_paper("Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents")
    citations = search.get_citations(target, limit=8) if target else []
    top_items = []
    for item in citations[:5]:
        top_items.append(
            {
                "title": item.get("title"),
                "paper_influence_score": item.get("paper_influence_score"),
                "paper_influence_level": item.get("paper_influence_level"),
                "scholar_citation_count": item.get("scholar_citation_count"),
                "publication_source": item.get("publication_source"),
                "publication_source_type": item.get("publication_source_type"),
                "scholar_link": item.get("scholar_link"),
            }
        )

    search.close()
    return {
        "target_title": target.get("title") if target else None,
        "sample_count": len(top_items),
        "samples": top_items,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    output = {
        "pdf_discovery": test_pdf_discovery(),
        "influence_scoring": test_influence_scoring(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
