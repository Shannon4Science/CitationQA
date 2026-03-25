"""Test report generation with charts embedded"""
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from backend.modules.report_generator import ReportGenerator
from backend.modules.chart_generator import ChartGenerator

charts_dir = os.path.join("backend", "charts")
os.makedirs(charts_dir, exist_ok=True)
cg = ChartGenerator(charts_dir)

analytics = {
    "time_distribution": {"labels": ["2025"], "values": [3]},
    "country_distribution_all": {"labels": ["China", "Germany"], "values": [2, 1]},
    "scholar_level_distribution": {"labels": ["Fellow"], "values": [2]},
    "citation_description_analysis": {
        "sentiment_distribution": {"positive": 40, "neutral": 50, "critical": 10},
        "citation_depth": {"core_citation": 35, "reference_citation": 45, "supplementary_citation": 20},
        "key_findings": ["Finding 1"],
    },
    "influence_prediction": {
        "trend_data": {"labels": ["2025","2026","2027"], "actual": [3,None,None], "forecast": [None,5,7]},
        "impact_scores": [{"label": "Innovation", "score": 72, "color_class": "fill-cyan"}],
        "prediction_commentary": "Test prediction commentary.",
        "prediction_metrics": [{"label": "2026", "value": "~5", "note": "forecast"}],
    },
    "insight_cards": [{"color": "teal", "icon": "T", "title": "Test", "body": "Test body"}],
    "citation_description_summary": "Test summary text.",
    "stats_summary": {"total_papers": 3, "unique_scholars": 2, "fellow_count": 2,
                      "country_count": 2, "self_citation_count": 0},
}
chart_assets = cg.generate_all(analytics, "rpt_test")
print(f"Charts generated: {len(chart_assets)}")

rg = ReportGenerator()
target = {"title": "Test Paper", "year": 2025, "venue": "Test Venue", "citation_count": 13,
          "influential_citation_count": 0, "authors": [{"name": "Author One"}],
          "abstract": "This is a test abstract."}
comp = {"overall_impact_score": 5, "overall_summary": "Test summary.", "key_findings": ["F1"],
        "citation_quality_distribution": {"method_reference": 2}, "depth_distribution": {"moderate": 3},
        "sentiment_distribution": {"positive": 2}, "influence_areas": ["AI"], "notable_citations": []}
evals = [{"citing_title": "Cite1", "citing_year": 2025, "citation_type": "method_reference",
          "citation_depth": "moderate", "citation_sentiment": "positive", "quality_score": 4,
          "summary": "Test eval", "detailed_analysis": "Detail", "fulltext_available": True,
          "content_type": "html", "citation_locations": [], "paper_influence_score": 5,
          "paper_influence_level": "medium", "paper_influence_reason": "", "scholar_citation_count": 0,
          "publication_source": "Test", "publication_source_type": "", "publication_domain": ""}]
scholars = [{"name": "Scholar One", "institution": "MIT", "country": "USA", "honors": "IEEE Fellow",
             "level_label": "Fellow", "is_top": True, "citing_paper_title": "Cite1", "title": "Prof"}]

result = rg.generate_report(target, comp, evals, "rpt_test", analytics, scholars, chart_assets)

md_path = result["md_path"]
pdf_path = result.get("pdf_path", "")

print(f"MD exists: {os.path.exists(md_path)}, size: {os.path.getsize(md_path)} bytes")
print(f"PDF path: {pdf_path}")
print(f"PDF exists: {os.path.exists(pdf_path)}")
if os.path.exists(pdf_path):
    print(f"PDF size: {os.path.getsize(pdf_path)} bytes")

md_text = open(md_path, "r", encoding="utf-8").read()
img_refs = md_text.count("![")
rel_path = "rpt_test_charts/" in md_text
print(f"MD image references: {img_refs}")
print(f"MD uses relative chart paths: {rel_path}")

if img_refs == 0:
    print("WARN: No images in MD!")
if not os.path.exists(pdf_path):
    print("WARN: PDF was not generated!")
else:
    print("ALL OK")
