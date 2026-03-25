"""
Earth-Agent 论文真实端到端测试
验证学者/地域/引用数据获取完整性
"""
import sys, os, json, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

os.environ['PYTHONIOENCODING'] = 'utf-8'

def test_earth_agent_enrichment():
    from backend.modules.search_llm_client import SearchLLMClient
    from backend.modules.scholar_enricher import ScholarEnricher
    from backend.modules.advanced_analytics import AdvancedAnalytics

    title = "Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents"

    print("=" * 60)
    print(f"Testing with: {title}")
    print("=" * 60)

    # Simulate 3 citing papers with real-ish authors
    evaluations = [
        {"citing_title": "GeoAgent: Multi-Modal Large Language Model-Based Agent for Geospatial Tasks",
         "citing_year": 2025, "citation_type": "method_reference", "citation_depth": "substantial",
         "citation_sentiment": "positive", "quality_score": 4,
         "summary": "Uses Earth-Agent as a key reference for agent-based geospatial analysis.",
         "fulltext_available": True, "scholar_citation_count": 5},
        {"citing_title": "Remote Sensing Foundation Models: A Survey",
         "citing_year": 2025, "citation_type": "background_mention", "citation_depth": "moderate",
         "citation_sentiment": "neutral", "quality_score": 3,
         "summary": "Mentions Earth-Agent in the survey of RS foundation models.",
         "fulltext_available": True, "scholar_citation_count": 20},
        {"citing_title": "An Intelligent Earth Observation Data Analysis Framework",
         "citing_year": 2025, "citation_type": "related_work_brief", "citation_depth": "moderate",
         "citation_sentiment": "positive", "quality_score": 3,
         "summary": "References Earth-Agent as related work in intelligent EO.",
         "fulltext_available": False, "scholar_citation_count": 3},
    ]

    citations = [
        {"title": evaluations[0]["citing_title"],
         "authors": [{"name": "Yifan Zhang"}, {"name": "Wei Liu"}],
         "venue": "arXiv", "year": 2025},
        {"title": evaluations[1]["citing_title"],
         "authors": [{"name": "Xiao Xiang Zhu"}, {"name": "Jan D. Wegner"}],
         "venue": "IEEE TGRS", "year": 2025},
        {"title": evaluations[2]["citing_title"],
         "authors": [{"name": "Jun Li"}, {"name": "Antonio Plaza"}],
         "venue": "Remote Sensing", "year": 2025},
    ]

    target_paper = {
        "title": title,
        "authors": [{"name": "Peilin Feng"}, {"name": "Zhutao Lv"}, {"name": "Weijia Li"}],
    }

    # Test 1: Scholar Enrichment
    print("\n--- Scholar Enrichment ---")
    enricher = ScholarEnricher(log_callback=lambda m: print(f"  [E] {m}"))
    result = enricher.enrich_citations(target_paper, evaluations, citations)

    enriched = result.get("enriched_citations", [])
    scholars = result.get("scholar_profiles", [])

    print(f"\nEnriched {len(enriched)} citations:")
    for i, e in enumerate(enriched):
        print(f"  [{i+1}] country={e.get('first_author_country', '?')}, "
              f"inst={e.get('first_author_institution', '?')}, "
              f"self_cite={e.get('is_self_citation')}, "
              f"renowned={e.get('scholar_info', {}).get('is_renowned')}")

    print(f"\nRenowned scholars: {len(scholars)}")
    for s in scholars:
        print(f"  {s.get('name')} | {s.get('institution')} | {s.get('country')} | "
              f"level={s.get('level_label')} | top={s.get('is_top')}")

    # Verify data exists
    countries_found = sum(1 for e in enriched if e.get("first_author_country"))
    insts_found = sum(1 for e in enriched if e.get("first_author_institution"))
    print(f"\nCountries found: {countries_found}/{len(enriched)}")
    print(f"Institutions found: {insts_found}/{len(enriched)}")
    assert countries_found > 0, "FAIL: No countries found for any author!"

    # Test 2: Advanced Analytics
    print("\n--- Advanced Analytics ---")
    analytics = AdvancedAnalytics(log_callback=lambda m: print(f"  [A] {m}"))

    comprehensive_eval = {
        "overall_impact_score": 5,
        "overall_summary": "Moderate impact paper.",
        "key_findings": ["Agent-based EO"],
    }

    analysis = analytics.run_full_analysis(target_paper, evaluations, result, comprehensive_eval)

    td = analysis.get("time_distribution", {})
    print(f"\nTime distribution: {td}")

    cd = analysis.get("country_distribution_all", {})
    print(f"Country distribution: {cd}")

    sld = analysis.get("scholar_level_distribution", {})
    print(f"Scholar level: {sld}")

    cda = analysis.get("citation_description_analysis", {})
    print(f"Citation desc keys: {list(cda.keys())}")
    print(f"  findings: {cda.get('key_findings', [])}")

    pred = analysis.get("influence_prediction", {})
    print(f"Prediction commentary: {pred.get('prediction_commentary', '')[:150]}")

    insights = analysis.get("insight_cards", [])
    print(f"Insight cards: {len(insights)}")

    stats = analysis.get("stats_summary", {})
    print(f"Stats: {json.dumps(stats, ensure_ascii=False)}")

    assert td.get("values"), "FAIL: No time distribution values!"
    assert cd.get("labels"), "FAIL: No country distribution data!"
    print("\n[ALL PASS] Earth-Agent enrichment and analytics working correctly")


if __name__ == "__main__":
    test_earth_agent_enrichment()
