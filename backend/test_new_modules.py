"""
新增模块集成测试
测试 search_llm_client / scholar_enricher / advanced_analytics / serp_api 扩展
"""
import sys, os, json, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def test_search_llm_client():
    from backend.modules.search_llm_client import SearchLLMClient
    client = SearchLLMClient()

    print("\n" + "="*60)
    print("TEST 1: search_query — Geoffrey Hinton basic info")
    print("="*60)
    r1 = client.search_query(
        "Who is Geoffrey Hinton? What university is he affiliated with? "
        "Answer briefly in 2-3 sentences."
    )
    print(f"Response length: {len(r1)} chars")
    print(f"Content: {r1[:600]}")
    assert len(r1) > 30, "Response too short"
    assert any(w in r1.lower() for w in ["hinton", "toronto", "google", "neural"]), \
        f"Response does not mention expected keywords: {r1[:200]}"
    print("[PASS] search_query returned meaningful content about Hinton")

    print("\n" + "="*60)
    print("TEST 2: search_json — Yann LeCun structured info")
    print("="*60)
    r2 = client.search_json(
        "Please return JSON with keys: name, institution, country, field "
        "for the researcher Yann LeCun. Only return JSON, no other text."
    )
    print(f"Type: {type(r2)}")
    print(f"Content: {json.dumps(r2, ensure_ascii=False, indent=2) if r2 else 'None'}")
    assert isinstance(r2, dict), f"Expected dict, got {type(r2)}"
    assert "name" in r2, "Missing 'name' key"
    assert "lecun" in r2.get("name", "").lower(), f"Name mismatch: {r2.get('name')}"
    print("[PASS] search_json returned valid structured data for LeCun")

    print("\n" + "="*60)
    print("TEST 3: search_scholar_info — Kaiming He")
    print("="*60)
    r3 = client.search_scholar_info("Kaiming He", "Deep Residual Learning for Image Recognition", "MIT")
    print(f"Result: {json.dumps(r3, ensure_ascii=False, indent=2)}")
    assert r3.get("name"), "Missing name"
    assert r3.get("country"), f"Missing country for Kaiming He"
    print(f"[PASS] scholar_info: name={r3['name']}, country={r3['country']}, "
          f"renowned={r3.get('is_renowned')}, level={r3.get('renowned_level')}")

    print("\n" + "="*60)
    print("TEST 4: search_author_country — Ashish Vaswani")
    print("="*60)
    r4 = client.search_author_country("Ashish Vaswani", "Attention Is All You Need")
    print(f"Result: {json.dumps(r4, ensure_ascii=False, indent=2)}")
    assert r4.get("institution") or r4.get("country"), "Both institution and country are empty"
    print(f"[PASS] author_country: institution={r4.get('institution')}, country={r4.get('country')}")


def test_serp_api_extensions():
    from backend.modules import serp_api

    print("\n" + "="*60)
    print("TEST 5: google_search — Geoffrey Hinton researcher")
    print("="*60)
    results = serp_api.google_search("Geoffrey Hinton researcher", num=3)
    print(f"Got {len(results)} results")
    for r in results[:3]:
        print(f"  - {r.get('title', '')[:80]}")
    assert len(results) > 0, "google_search returned no results"
    print("[PASS] google_search returned results")

    print("\n" + "="*60)
    print("TEST 6: google_scholar_author_search — Yann LeCun")
    print("="*60)
    profiles = serp_api.google_scholar_author_search("Yann LeCun")
    print(f"Got {len(profiles)} profiles")
    for p in profiles[:3]:
        print(f"  - {p.get('name', '')}, affil={p.get('affiliation', '')[:60]}")
    if len(profiles) > 0:
        print("[PASS] google_scholar_author_search returned profiles")
    else:
        print("[WARN] No profiles returned (fallback may have failed)")

    print("\n" + "="*60)
    print("TEST 7: search_author_info — Kaiming He")
    print("="*60)
    info = serp_api.search_author_info("Kaiming He", "Deep Residual Learning")
    print(f"Info: {json.dumps(info, ensure_ascii=False, indent=2)}")
    assert info.get("name") == "Kaiming He", f"Name mismatch: {info.get('name')}"
    print(f"[PASS] search_author_info: institution={info.get('institution')}, cited_by={info.get('cited_by')}")

    print("\n" + "="*60)
    print("TEST 8: google_ai_mode_query")
    print("="*60)
    ai_result = serp_api.google_ai_mode_query("Who is Geoffrey Hinton and what are his contributions to deep learning?")
    if ai_result:
        print(f"AI Mode text length: {len(ai_result.get('text', ''))}")
        print(f"References: {len(ai_result.get('references', []))}")
        print(f"Text preview: {ai_result.get('text', '')[:300]}")
        print("[PASS] google_ai_mode_query returned content")
    else:
        print("[WARN] google_ai_mode_query returned None (may be unsupported or rate limited)")


def test_scholar_enricher():
    from backend.modules.scholar_enricher import ScholarEnricher

    print("\n" + "="*60)
    print("TEST 9: ScholarEnricher — enrich mock citations")
    print("="*60)
    enricher = ScholarEnricher(log_callback=lambda msg: print(f"  [enricher] {msg}"))

    target_paper = {
        "title": "Attention Is All You Need",
        "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
    }

    evaluations = [
        {
            "citing_title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "citing_year": 2019,
            "citation_type": "method_reference",
            "citation_depth": "substantial",
            "citation_sentiment": "positive",
            "quality_score": 5,
            "summary": "BERT builds directly on the Transformer architecture proposed in the target paper.",
            "fulltext_available": True,
        },
        {
            "citing_title": "A Survey on Transformers in NLP",
            "citing_year": 2023,
            "citation_type": "background_mention",
            "citation_depth": "moderate",
            "citation_sentiment": "neutral",
            "quality_score": 3,
            "summary": "This survey mentions the Transformer as a foundational architecture.",
            "fulltext_available": True,
        },
    ]

    citations = [
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "authors": [{"name": "Jacob Devlin"}, {"name": "Ming-Wei Chang"}],
            "venue": "NAACL 2019",
            "year": 2019,
        },
        {
            "title": "A Survey on Transformers in NLP",
            "authors": [{"name": "Some Author"}],
            "venue": "ACM Computing Surveys",
            "year": 2023,
        },
    ]

    result = enricher.enrich_citations(target_paper, evaluations, citations)
    print(f"\nEnrichment result:")
    print(f"  Scholar profiles: {len(result.get('scholar_profiles', []))}")
    print(f"  Self-citation indices: {result.get('self_citation_indices', [])}")
    print(f"  Self-citation count: {result.get('self_citation_count', 0)}")
    print(f"  Enriched citations: {len(result.get('enriched_citations', []))}")

    for i, e in enumerate(result.get("enriched_citations", [])):
        print(f"  Citation {i+1}: country={e.get('first_author_country')}, "
              f"institution={e.get('first_author_institution')}, "
              f"self_cite={e.get('is_self_citation')}")

    for s in result.get("scholar_profiles", []):
        print(f"  Scholar: {s.get('name')} | {s.get('institution')} | "
              f"level={s.get('level_label')} | top={s.get('is_top')}")

    print("[PASS] ScholarEnricher completed without errors")


def test_advanced_analytics():
    from backend.modules.advanced_analytics import AdvancedAnalytics

    print("\n" + "="*60)
    print("TEST 10: AdvancedAnalytics — run full analysis on mock data")
    print("="*60)
    analytics = AdvancedAnalytics(log_callback=lambda msg: print(f"  [analytics] {msg}"))

    target_paper = {"title": "Attention Is All You Need", "abstract": "Dominant models use recurrent..."}

    evaluations = [
        {"citing_title": "BERT", "citing_year": 2019, "citation_type": "method_reference",
         "citation_depth": "substantial", "citation_sentiment": "positive", "quality_score": 5,
         "summary": "BERT builds on the Transformer.", "fulltext_available": True,
         "scholar_citation_count": 50000, "citation_locations": [{"section": "Method", "context": "We use Transformer"}]},
        {"citing_title": "GPT-2", "citing_year": 2019, "citation_type": "method_reference",
         "citation_depth": "substantial", "citation_sentiment": "positive", "quality_score": 5,
         "summary": "GPT-2 uses the Transformer decoder.", "fulltext_available": True,
         "scholar_citation_count": 30000, "citation_locations": [{"section": "Introduction"}]},
        {"citing_title": "ViT", "citing_year": 2020, "citation_type": "method_reference",
         "citation_depth": "substantial", "citation_sentiment": "positive", "quality_score": 4,
         "summary": "ViT applies Transformer to images.", "fulltext_available": True,
         "scholar_citation_count": 20000},
        {"citing_title": "Survey 2024", "citing_year": 2024, "citation_type": "background_mention",
         "citation_depth": "moderate", "citation_sentiment": "neutral", "quality_score": 3,
         "summary": "This survey covers Transformer variants.", "fulltext_available": True,
         "scholar_citation_count": 100},
    ]

    scholar_data = {
        "enriched_citations": [
            {"first_author_country": "USA", "first_author_institution": "Google", "scholar_info": {"is_renowned": True, "renowned_level": "industry_leader"}},
            {"first_author_country": "USA", "first_author_institution": "OpenAI", "scholar_info": {"is_renowned": True, "renowned_level": "industry_leader"}},
            {"first_author_country": "USA", "first_author_institution": "Google Brain", "scholar_info": {"is_renowned": False, "renowned_level": "none"}},
            {"first_author_country": "China", "first_author_institution": "Tsinghua University", "scholar_info": {"is_renowned": False, "renowned_level": "none"}},
        ],
        "scholar_profiles": [
            {"name": "Jacob Devlin", "country": "USA", "is_top": False, "level": "industry_leader"},
            {"name": "Alec Radford", "country": "USA", "is_top": False, "level": "industry_leader"},
        ],
        "self_citation_count": 0,
    }

    comprehensive_eval = {
        "overall_impact_score": 9,
        "overall_summary": "Highly influential paper.",
        "key_findings": ["Foundational architecture"],
    }

    result = analytics.run_full_analysis(target_paper, evaluations, scholar_data, comprehensive_eval)

    print(f"\nAnalysis result keys: {list(result.keys())}")
    td = result.get("time_distribution", {})
    print(f"  Time distribution: labels={td.get('labels')}, values={td.get('values')}")

    cd = result.get("country_distribution_all", {})
    print(f"  Country distribution: {cd}")

    sld = result.get("scholar_level_distribution", {})
    print(f"  Scholar level dist: {sld}")

    cda = result.get("citation_description_analysis", {})
    print(f"  Citation desc analysis keys: {list(cda.keys()) if cda else 'None'}")
    print(f"    key_findings: {cda.get('key_findings', [])[:2]}")

    pred = result.get("influence_prediction", {})
    print(f"  Prediction keys: {list(pred.keys()) if pred else 'None'}")
    print(f"    commentary: {pred.get('prediction_commentary', '')[:150]}")

    insights = result.get("insight_cards", [])
    print(f"  Insight cards: {len(insights)}")
    for ins in insights[:2]:
        icon = ins.get('icon', '').encode('ascii', 'replace').decode()
        body_clean = ins.get('body', '').encode('ascii', 'replace').decode()[:80]
        print(f"    {icon} {ins.get('title', '')}: {body_clean}")

    summary = result.get("citation_description_summary", "")
    print(f"  Citation summary length: {len(summary)} chars")

    stats = result.get("stats_summary", {})
    print(f"  Stats: papers={stats.get('total_papers')}, scholars={stats.get('unique_scholars')}, "
          f"countries={stats.get('country_count')}")

    assert td.get("labels"), "No time distribution labels"
    assert result.get("citation_description_analysis"), "No citation description analysis"
    assert result.get("influence_prediction"), "No influence prediction"
    print("\n[PASS] AdvancedAnalytics completed without errors")


if __name__ == "__main__":
    print("="*60)
    print("Running integration tests for new modules")
    print("="*60)

    test_search_llm_client()
    test_serp_api_extensions()
    test_scholar_enricher()
    test_advanced_analytics()

    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60)
