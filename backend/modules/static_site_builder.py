"""
Static site builder: exports CitationQA analysis results as JSON
and triggers Astro build.
"""

import os
import json
import subprocess
import logging
from datetime import datetime

logger = logging.getLogger("citation_analyzer.static_builder")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
DATA_DIR = os.path.join(FRONTEND_DIR, "src", "data")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")


def _build_graph_data(paper, evaluations, scholar_profiles):
    """Build a D3-compatible graph from analysis results."""
    nodes = []
    edges = []

    paper_title = paper.get("title", "Unknown")
    root_id = "root"
    nodes.append({
        "id": root_id,
        "label": paper_title[:40],
        "type": "root",
        "size": 30,
        "year": paper.get("year"),
        "score": None,
    })

    for i, ev in enumerate(evaluations):
        cid = f"c{i}"
        score = ev.get("quality_score", 0)
        nodes.append({
            "id": cid,
            "label": (ev.get("citing_title") or "Unknown")[:30],
            "type": "citation",
            "size": max(8, score * 4),
            "year": ev.get("citing_year"),
            "score": score,
        })
        edges.append({"source": cid, "target": root_id, "type": "cites"})

    seen_authors = set()
    for sp in (scholar_profiles or []):
        name = sp.get("name", "")
        if not name or name in seen_authors:
            continue
        seen_authors.add(name)
        aid = f"a{len(seen_authors)}"
        nodes.append({
            "id": aid,
            "label": name[:20],
            "type": "author",
            "size": 10,
        })
        citing = sp.get("citing_paper", "")
        for i, ev in enumerate(evaluations):
            if citing and citing.lower() in (ev.get("citing_title") or "").lower():
                edges.append({"source": aid, "target": f"c{i}", "type": "authored"})
                break

    domains = set()
    for ev in evaluations:
        d = ev.get("publication_domain")
        if d and d not in domains:
            domains.add(d)
            cid_concept = f"con{len(domains)}"
            nodes.append({
                "id": cid_concept,
                "label": d[:20],
                "type": "concept",
                "size": 14,
            })
            for j, ev2 in enumerate(evaluations):
                if ev2.get("publication_domain") == d:
                    edges.append({"source": f"c{j}", "target": cid_concept, "type": "about"})

    return {"nodes": nodes, "edges": edges}


def export_report_json(task):
    """Serialize a TaskData instance to a report.json file."""
    paper = task.paper or {}
    evaluations = task.evaluations or []
    ce = task.comprehensive_eval or {}
    aa = task.advanced_analytics or {}
    scholars = task.scholar_profiles or []

    graph_data = _build_graph_data(paper, evaluations, scholars)

    report = {
        "paper": {
            "title": paper.get("title", ""),
            "authors": paper.get("authors", []),
            "year": paper.get("year"),
            "venue": paper.get("venue", paper.get("publication_source", "")),
            "total_citations": paper.get("total_citations", paper.get("citationCount", 0)),
            "doi": paper.get("doi", ""),
        },
        "comprehensive_eval": ce,
        "evaluations": evaluations,
        "advanced_analytics": aa,
        "scholar_profiles": scholars,
        "graph_data": graph_data,
        "generated_at": datetime.now().isoformat(),
        "task_id": task.task_id,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, "report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"Exported report JSON to {json_path}")
    return json_path


def build_static_site():
    """Run Astro build in the frontend directory."""
    if not os.path.isdir(FRONTEND_DIR):
        raise FileNotFoundError(f"Frontend directory not found: {FRONTEND_DIR}")

    logger.info("Running Astro build...")
    build_env = os.environ.copy()
    base_path = os.environ.get("BASE_PATH", "")
    if base_path:
        build_env["ASTRO_BASE"] = base_path

    result = subprocess.run(
        "npm run build",
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        shell=True,
        env=build_env,
    )
    if result.returncode != 0:
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        logger.error(f"Astro build failed (code {result.returncode}):\n{combined}")
        raise RuntimeError(f"Astro build failed: {combined.strip()[-800:]}")

    logger.info("Astro build completed successfully")
    return DIST_DIR
