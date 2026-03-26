"""
Citation Quality Analyzer - Flask后端服务
SSE长连接 + 并发处理 + 任务恢复 + 5源检索 + 高级分析
"""

import os
import sys
import json
import uuid
import logging
import threading
import asyncio
import time
import queue
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.modules.paper_search import UnifiedPaperSearch
from backend.modules.fulltext_fetcher import FulltextFetcher
from backend.modules.llm_evaluator import LLMEvaluator
from backend.modules.report_generator import ReportGenerator
from backend.modules.scholar_enricher import ScholarEnricher
from backend.modules.advanced_analytics import AdvancedAnalytics
from backend.modules.chart_generator import ChartGenerator
from backend.modules.static_site_builder import export_report_json, build_static_site
import backend.config as backend_config
from backend.config import APP_SETTINGS

# ===== 配置 =====
BASE_DIR = os.path.dirname(__file__)
LOG_DIR = os.path.join(BASE_DIR, "logs")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CHARTS_DIR = os.path.join(BASE_DIR, "charts")

# 并发数上限
CONCURRENCY_LIMIT = int(APP_SETTINGS.get("concurrency_limit", 10))

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)

# ===== 日志配置 =====
def setup_logging():
    """配置详细的日志记录"""
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("citation_analyzer.app")

# ===== Flask应用 =====
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
CORS(app)

@app.context_processor
def inject_base_path():
    return dict(base_path=BASE_PATH)

# ===== 任务存储 =====
tasks = {}  # task_id -> TaskData


class TaskData:
    """任务数据"""
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = "created"
        self.progress = 0
        self.stage = "初始化"
        self.stage_short = "初始化"
        self.paper = None
        self.citations = []
        self.selected_citations = []
        self.evaluations = []
        self.comprehensive_eval = None
        self.report_paths = None
        self.advanced_analytics = None
        self.scholar_profiles = []
        self.chart_assets = {}
        self.error = None
        self.logs = []
        self.log_cursor = 0
        self.analyzed = 0
        self.fulltext_count = 0
        self.abstract_count = 0
        self.search_llm_count = 0
        self.scholar_current = 0
        self.scholar_total = 0
        self.scholar_name = ""
        self.created_at = datetime.now()

        # SSE事件队列
        self.sse_queues = []  # 多个客户端可以同时监听

        # 任务专属日志
        self.task_logger = logging.getLogger(f"task.{task_id}")
        task_log_file = os.path.join(LOG_DIR, f"task_{task_id}.log")
        handler = logging.FileHandler(task_log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        self.task_logger.addHandler(handler)
        self.task_logger.setLevel(logging.DEBUG)
        self.task_logger.propagate = False

    @staticmethod
    def _emit_terminal_log(level: str, task_id: str, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} [{level.upper()}] [Task {task_id}] {message}", flush=True)

    def add_log(self, message: str, level: str = "info"):
        self.logs.append({"message": message, "level": level, "time": datetime.now().isoformat()})
        getattr(self.task_logger, level, self.task_logger.info)(message)
        self._emit_terminal_log(level, self.task_id, message)
        self._push_sse({"type": "log", "message": message, "level": level})

    def get_new_logs(self):
        new_logs = self.logs[self.log_cursor:]
        self.log_cursor = len(self.logs)
        return new_logs

    def push_progress(self):
        """推送进度更新"""
        self._push_sse({
            "type": "progress",
            "progress": self.progress,
            "stage": self.stage,
            "stage_short": self.stage_short,
            "analyzed": self.analyzed,
            "fulltext_count": self.fulltext_count,
            "abstract_count": self.abstract_count,
            "search_llm_count": self.search_llm_count,
            "scholar_current": self.scholar_current,
            "scholar_total": self.scholar_total,
            "scholar_name": self.scholar_name,
        })

    def push_completed(self):
        """推送完成事件"""
        self._push_sse({
            "type": "completed",
            "progress": 100,
            "stage": "分析完成",
            "stage_short": "完成",
            "analyzed": self.analyzed,
            "fulltext_count": self.fulltext_count,
            "abstract_count": self.abstract_count,
            "search_llm_count": self.search_llm_count,
            "comprehensive_eval": self.comprehensive_eval,
            "evaluations": self.evaluations,
            "report_paths": self.report_paths,
            "advanced_analytics": self.advanced_analytics,
            "scholar_profiles": self.scholar_profiles,
            "chart_assets": self.chart_assets,
        })

    def push_error(self, error_msg):
        """推送错误事件"""
        self._push_sse({"type": "error", "error": error_msg})

    def _push_sse(self, data):
        dead_queues = []
        for q in self.sse_queues:
            try:
                q.put_nowait(data)
            except Exception:
                dead_queues.append(q)
        for q in dead_queues:
            self.sse_queues.remove(q)


# ===== API路由 =====

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config', methods=['GET'])
def get_config():
    """Return current config (masks sensitive keys)."""
    def mask(val):
        if not val or len(val) < 8:
            return val
        return val[:4] + '*' * (len(val) - 8) + val[-4:]

    return jsonify({
        "llm": {
            "model": backend_config.LLM_SETTINGS["model"],
            "api_key": mask(backend_config.LLM_SETTINGS["api_key"]),
            "primary_base_url": backend_config.LLM_SETTINGS["primary_base_url"],
            "secondary_base_url": backend_config.LLM_SETTINGS["secondary_base_url"],
            "search_timeout": backend_config.LLM_SETTINGS.get("search_timeout", 180),
        },
        "serpapi": {
            "api_key": mask(backend_config.SERPAPI_SETTINGS["api_key"]),
        },
        "semantic_scholar": {
            "api_key": mask(backend_config.SEMANTIC_SCHOLAR_SETTINGS.get("api_key", "")),
        },
        "adsabs": {
            "api_key": mask(backend_config.ADSABS_SETTINGS.get("api_key", "")),
        },
        "mineru": {
            "api_token": mask(backend_config.MINERU_SETTINGS.get("api_token", "")),
        },
        "proxy": {
            "fallback_proxy": backend_config.PROXY_SETTINGS.get("fallback_proxy", ""),
        },
    })


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update config settings at runtime."""
    data = request.json or {}

    if "llm" in data:
        llm = data["llm"]
        if llm.get("model"):
            backend_config.LLM_SETTINGS["model"] = llm["model"]
        if llm.get("api_key") and '*' not in llm["api_key"]:
            backend_config.LLM_SETTINGS["api_key"] = llm["api_key"]
        if llm.get("primary_base_url"):
            backend_config.LLM_SETTINGS["primary_base_url"] = llm["primary_base_url"]
        if llm.get("secondary_base_url") is not None:
            backend_config.LLM_SETTINGS["secondary_base_url"] = llm["secondary_base_url"]
        if llm.get("search_timeout"):
            backend_config.LLM_SETTINGS["search_timeout"] = int(llm["search_timeout"])

    if "serpapi" in data:
        serp = data["serpapi"]
        if serp.get("api_key") and '*' not in serp["api_key"]:
            backend_config.SERPAPI_SETTINGS["api_key"] = serp["api_key"]

    if "semantic_scholar" in data:
        s2 = data["semantic_scholar"]
        if s2.get("api_key") is not None and '*' not in (s2.get("api_key") or ""):
            backend_config.SEMANTIC_SCHOLAR_SETTINGS["api_key"] = s2["api_key"]

    if "adsabs" in data:
        ads = data["adsabs"]
        if ads.get("api_key") is not None and '*' not in (ads.get("api_key") or ""):
            backend_config.ADSABS_SETTINGS["api_key"] = ads["api_key"]

    if "mineru" in data:
        mineru = data["mineru"]
        if mineru.get("api_token") is not None and '*' not in (mineru.get("api_token") or ""):
            backend_config.MINERU_SETTINGS["api_token"] = mineru["api_token"]

    if "proxy" in data:
        proxy = data["proxy"]
        if proxy.get("fallback_proxy") is not None:
            backend_config.PROXY_SETTINGS["fallback_proxy"] = proxy["fallback_proxy"]

    return jsonify({"status": "ok"})


@app.route('/api/search', methods=['POST'])
def search_paper():
    """搜索论文并获取被引列表"""
    data = request.json
    title = data.get('title', '').strip()

    if not title:
        return jsonify({"error": "请输入论文标题"}), 400

    task_id = str(uuid.uuid4())[:8]
    task = TaskData(task_id)
    tasks[task_id] = task

    task.add_log(f"开始搜索论文: {title}")
    task.status = "searching"

    try:
        search = UnifiedPaperSearch()

        paper = search.search_paper(title)
        if not paper:
            task.add_log("未找到论文", "error")
            search.close()
            return jsonify({"error": f"未找到论文: {title}"}), 404

        task.paper = paper
        task.add_log(f"找到论文: {paper.get('title', 'N/A')}, 被引: {paper.get('citation_count', 0)}")

        citations = search.get_citations(paper, limit=1000)
        task.citations = citations
        raw_count = int(paper.get("citation_count", 0) or 0)
        actual_count = len(citations)
        # 论文信息确认区和后续步骤都统一使用 5 源聚合去重后的真实数量。
        paper["raw_citation_count"] = raw_count
        paper["dedup_citation_count"] = actual_count
        paper["citation_count"] = actual_count
        if search.last_citation_stats:
            paper["citation_source_stats"] = search.last_citation_stats
            source_counts = search.last_citation_stats.get("source_counts", {})
            task.add_log(
                "5源原始返回量: "
                f"SS={source_counts.get('semantic_scholar', 0)}, "
                f"PubMed={source_counts.get('pubmed', 0)}, "
                f"GS={source_counts.get('serpapi', 0)}, "
                f"ADS={source_counts.get('adsabs', 0)}"
            )
        task.paper = dict(paper)
        if raw_count and raw_count != actual_count:
            task.add_log(f"源接口参考被引数为 {raw_count}，5源聚合去重后真实被引数为 {actual_count}")
        task.add_log(f"5源聚合去重后获取到 {actual_count} 篇被引论文")

        search.close()
        response_paper = dict(task.paper or {})

        return jsonify({
            "task_id": task_id,
            "paper": response_paper,
            "citations": citations[:200],
            "total_citations": actual_count
        })

    except Exception as e:
        task.add_log(f"搜索失败: {str(e)}", "error")
        logger.exception("搜索失败")
        return jsonify({"error": f"搜索失败: {str(e)}"}), 500


@app.route('/api/evaluate', methods=['POST'])
def start_evaluation():
    """开始评估"""
    data = request.json
    task_id = data.get('task_id')
    selected_indices = data.get('selected_indices', [])

    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]

    if selected_indices:
        task.selected_citations = [task.citations[i] for i in selected_indices if i < len(task.citations)]
    else:
        task.selected_citations = task.citations[:100]

    task.add_log(f"开始评估 {len(task.selected_citations)} 篇被引论文 (并发数: {CONCURRENCY_LIMIT})")
    task.status = "evaluating"

    thread = threading.Thread(target=run_evaluation_concurrent, args=(task,))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "count": len(task.selected_citations)})


@app.route('/api/stream/<task_id>')
def stream_progress(task_id):
    """SSE长连接进度推送"""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]
    q = queue.Queue(maxsize=500)
    task.sse_queues.append(q)

    def generate():
        try:
            # 先发送当前状态
            yield f"data: {json.dumps({'type': 'progress', 'progress': task.progress, 'stage': task.stage, 'stage_short': task.stage_short, 'analyzed': task.analyzed, 'fulltext_count': task.fulltext_count, 'abstract_count': task.abstract_count, 'search_llm_count': task.search_llm_count})}\n\n"

            # 发送历史日志
            for log in task.logs:
                yield f"data: {json.dumps({'type': 'log', 'message': log['message'], 'level': log['level']})}\n\n"

            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                    if data.get('type') in ('completed', 'error'):
                        break
                except queue.Empty:
                    # 发送心跳
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    if task.status in ('completed', 'error'):
                        break
        finally:
            if q in task.sse_queues:
                task.sse_queues.remove(q)

    return Response(generate(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    """获取评估进度（轮询备用）"""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]

    response = {
        "status": task.status,
        "progress": task.progress,
        "stage": task.stage,
        "stage_short": task.stage_short,
        "analyzed": task.analyzed,
        "fulltext_count": task.fulltext_count,
        "abstract_count": task.abstract_count,
        "search_llm_count": task.search_llm_count,
        "new_logs": task.get_new_logs(),
        "error": task.error,
        "paper": task.paper
    }

    if task.status == "completed":
        response["comprehensive_eval"] = task.comprehensive_eval
        response["evaluations"] = task.evaluations
        response["report_paths"] = task.report_paths
        response["advanced_analytics"] = task.advanced_analytics
        response["scholar_profiles"] = task.scholar_profiles
        response["chart_assets"] = task.chart_assets

    return jsonify(response)


@app.route('/api/chart/<path:filename>')
def serve_chart(filename):
    """提供图表文件"""
    path = os.path.join(CHARTS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "图表不存在"}), 404
    return send_file(path, mimetype='image/png')


@app.route('/api/download/<task_id>/<format>')
def download_report(task_id, format):
    """下载报告"""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]

    if not task.report_paths:
        return jsonify({"error": "报告尚未生成"}), 404

    if format == 'md':
        path = task.report_paths.get('md_path')
        filename = task.report_paths.get('md_filename')
        mimetype = 'text/markdown'
    elif format == 'pdf':
        path = task.report_paths.get('pdf_path')
        filename = task.report_paths.get('pdf_filename')
        mimetype = 'application/pdf'
    else:
        return jsonify({"error": "不支持的格式"}), 400

    if not path or not os.path.exists(path):
        return jsonify({"error": "文件不存在"}), 404

    return send_file(path, as_attachment=True, download_name=filename, mimetype=mimetype)


@app.route('/api/export/<task_id>')
def export_report(task_id):
    """Export complete analysis results as report.json for the static site."""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]
    if task.status != "completed":
        return jsonify({"error": "分析尚未完成", "status": task.status}), 400

    try:
        json_path = export_report_json(task)
        with open(json_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        return jsonify(report)
    except Exception as e:
        logger.exception(f"Export failed for task {task_id}")
        return jsonify({"error": f"导出失败: {str(e)}"}), 500


@app.route('/api/report/<task_id>')
def view_report(task_id):
    """Build and serve the Astro static report."""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]
    if task.status != "completed":
        return jsonify({"error": "分析尚未完成", "status": task.status}), 400

    try:
        export_report_json(task)
        build_static_site()
        dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
        index_path = os.path.join(dist_path, "index.html")
        if os.path.isfile(index_path):
            return send_file(index_path)
        return jsonify({"error": "构建产物未找到"}), 500
    except Exception as e:
        logger.exception(f"Report build failed for task {task_id}")
        return jsonify({"error": f"报告构建失败: {str(e)}"}), 500


@app.route('/_astro/<path:filename>')
def astro_assets(filename):
    """Serve Astro build assets from /_astro/ path."""
    dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist", "_astro")
    return send_file(os.path.join(dist_path, filename))




# ===== 并发评估工作流 =====

def run_evaluation_concurrent(task: TaskData):
    """在后台线程中使用asyncio并发执行评估"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_evaluation(task))
    except Exception as e:
        task.error = str(e)
        task.status = "error"
        task.add_log(f"评估工作流异常: {str(e)}", "error")
        task.push_error(str(e))
        logger.exception(f"Task {task.task_id} failed")
    finally:
        loop.close()


async def _async_evaluation(task: TaskData):
    """异步并发评估工作流"""
    total = len(task.selected_citations)
    task.add_log(f"评估工作流开始，共 {total} 篇论文，并发数: {CONCURRENCY_LIMIT}")

    evaluator = LLMEvaluator()
    if not evaluator.client:
        evaluator._init_client()
        if not evaluator.client:
            task.error = "LLM服务不可用"
            task.status = "error"
            task.add_log("LLM服务不可用，评估终止", "error")
            task.push_error("LLM服务不可用")
            return

    # 阶段1: 并发搜索优先评估，再按需抓取全文
    task.stage = "正在并发搜索优先评估引用质量..."
    task.stage_short = "并发分析"
    task.push_progress()

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    results = [None] * total
    lock = asyncio.Lock()

    async def process_one(i, citation):
        async with semaphore:
            title = citation.get("title", "N/A")
            task.add_log(f"[{i+1}/{total}] 开始处理: {title[:60]}...")

            loop = asyncio.get_event_loop()
            fetcher = None
            eval_result = None
            citation_contexts = []
            fulltext = ""
            annotated_content = ""
            content_type = "none"
            pdf_path = None
            source_url = None

            def build_candidate_link_hints():
                hints = []
                arxiv_id_local = citation.get("arxiv_id") or citation.get("externalIds", {}).get("ArXiv")
                if arxiv_id_local:
                    hints.extend([
                        f"https://arxiv.org/abs/{arxiv_id_local}",
                        f"https://arxiv.org/pdf/{arxiv_id_local}",
                        f"https://arxiv.org/html/{arxiv_id_local}",
                    ])
                if citation.get("doi"):
                    hints.append(f"https://doi.org/{citation['doi']}")
                if citation.get("open_access_pdf"):
                    hints.append(citation.get("open_access_pdf"))
                return [link for link in hints if link]

            extra_candidate_links = build_candidate_link_hints()

            try:
                search_first = await loop.run_in_executor(
                    None, evaluator.evaluate_single_citation,
                    task.paper, citation, "", "search_only",
                    None,
                    extra_candidate_links if extra_candidate_links else None,
                    "", True, True
                )
            except Exception as e:
                task.add_log(f"[{i+1}/{total}] 首轮 LLM search 异常: {e}", "warning")
                search_first = None

            if isinstance(search_first, dict) and search_first.get("evaluation_method") == "web_search":
                async with lock:
                    task.search_llm_count += 1
                task.add_log(f"[{i+1}/{total}] 首轮 LLM search 成功，跳过全文抓取", "success")
                eval_result = search_first

            if eval_result is None:
                fetcher = FulltextFetcher(download_dir=os.path.join(DOWNLOAD_DIR, task.task_id))
                try:
                    ctx_result = await loop.run_in_executor(
                        None, fetcher.fetch_fulltext_with_citation_context,
                        citation, task.paper.get("title", "")
                    )
                    fulltext = ctx_result.get("fulltext") or ""
                    annotated_content = ctx_result.get("annotated_content") or fulltext
                    content_type = ctx_result.get("content_type", "none")
                    pdf_path = ctx_result.get("pdf_path")
                    source_url = ctx_result.get("fulltext_url")
                    citation_contexts = ctx_result.get("citation_contexts", [])
                    if not fulltext and content_type == "none":
                        fulltext = citation.get("abstract", "")
                        annotated_content = fulltext
                        content_type = "abstract_only"
                except Exception as e:
                    task.add_log(f"[{i+1}/{total}] 全文获取失败: {e}", "warning")
                    fulltext = citation.get("abstract", "")
                    annotated_content = fulltext
                    content_type = "abstract_only"
                    pdf_path = None
                    source_url = None

            # 获取全文链接信息
            fulltext_urls = {}
            arxiv_id = citation.get("arxiv_id") or citation.get("externalIds", {}).get("ArXiv")
            if arxiv_id:
                fulltext_urls["html_url"] = f"https://arxiv.org/html/{arxiv_id}"
                fulltext_urls["pdf_url"] = f"https://arxiv.org/pdf/{arxiv_id}"
                fulltext_urls["fulltext_url"] = fulltext_urls["html_url"]
            if citation.get("open_access_pdf") and "pdf_url" not in fulltext_urls:
                fulltext_urls["pdf_url"] = citation.get("open_access_pdf")
            if source_url:
                fulltext_urls["fulltext_url"] = source_url
                if content_type == "pdf":
                    fulltext_urls["pdf_url"] = source_url
            elif citation.get("doi") and "fulltext_url" not in fulltext_urls:
                fulltext_urls["fulltext_url"] = f"https://doi.org/{citation['doi']}"

            if eval_result is None:
                if content_type in ("html", "pdf"):
                    async with lock:
                        task.fulltext_count += 1
                    task.add_log(f"[{i+1}/{total}] 全文获取成功 ({content_type})", "success")
                else:
                    async with lock:
                        task.abstract_count += 1
                    task.add_log(f"[{i+1}/{total}] 仅获取到摘要", "warning")

                second_search_hint = (annotated_content or fulltext or "")[:2200]
                try:
                    search_second = await loop.run_in_executor(
                        None, evaluator.evaluate_single_citation,
                        task.paper, citation, "", content_type,
                        citation_contexts if citation_contexts else None,
                        list(fulltext_urls.values()) if fulltext_urls else extra_candidate_links or None,
                        second_search_hint, True, True
                    )
                except Exception as e:
                    task.add_log(f"[{i+1}/{total}] 二轮 LLM search 异常: {e}", "warning")
                    search_second = None

                if isinstance(search_second, dict) and search_second.get("evaluation_method") == "web_search":
                    async with lock:
                        task.search_llm_count += 1
                    task.add_log(f"[{i+1}/{total}] 二轮 LLM search 成功，使用联网证据结果", "success")
                    eval_result = search_second

            try:
                if eval_result is None:
                    eval_result = await loop.run_in_executor(
                        None, evaluator.evaluate_single_citation,
                        task.paper, citation, annotated_content or fulltext or "", content_type,
                        citation_contexts if citation_contexts else None,
                        list(fulltext_urls.values()) if fulltext_urls else extra_candidate_links or None,
                        (annotated_content or fulltext or "")[:2200], False, False
                    )
                # 添加全文链接
                eval_result.update(fulltext_urls)
                eval_result.update({
                    "paper_influence_score": citation.get("paper_influence_score", 0),
                    "paper_influence_level": citation.get("paper_influence_level", "未知"),
                    "paper_influence_reason": citation.get("paper_influence_reason", ""),
                    "scholar_citation_count": citation.get("scholar_citation_count", 0),
                    "publication_source": citation.get("publication_source", ""),
                    "publication_source_type": citation.get("publication_source_type", ""),
                    "publication_domain": citation.get("publication_domain", ""),
                    "scholar_link": citation.get("scholar_link", ""),
                })
                results[i] = eval_result
                score = eval_result.get("quality_score", 0)
                ctype = eval_result.get("citation_type", "unknown")
                task.add_log(f"[{i+1}/{total}] 评估完成: 类型={ctype}, 评分={score}/5")
            except Exception as e:
                task.add_log(f"[{i+1}/{total}] LLM评估失败: {e}", "error")
                results[i] = {
                    "citing_title": title,
                    "citing_year": citation.get("year"),
                    "content_type": content_type,
                    "fulltext_available": content_type in ("html", "pdf"),
                    "citation_type": "unknown",
                    "citation_depth": "unknown",
                    "citation_sentiment": "unknown",
                    "quality_score": 0,
                    "summary": f"评估失败: {str(e)}",
                    "detailed_analysis": "LLM评估过程中出现错误",
                    "citation_locations": [],
                    "paper_influence_score": citation.get("paper_influence_score", 0),
                    "paper_influence_level": citation.get("paper_influence_level", "未知"),
                    "paper_influence_reason": citation.get("paper_influence_reason", ""),
                    "scholar_citation_count": citation.get("scholar_citation_count", 0),
                    "publication_source": citation.get("publication_source", ""),
                    "publication_source_type": citation.get("publication_source_type", ""),
                    "publication_domain": citation.get("publication_domain", ""),
                    "scholar_link": citation.get("scholar_link", ""),
                    **fulltext_urls
                }

            async with lock:
                task.analyzed += 1
                task.progress = (task.analyzed / total) * 80
                task.push_progress()

            try:
                if fetcher:
                    fetcher.close()
            except Exception:
                pass

    # 创建所有并发任务
    tasks_list = [process_one(i, c) for i, c in enumerate(task.selected_citations)]
    await asyncio.gather(*tasks_list, return_exceptions=True)

    task.evaluations = [r for r in results if r is not None]
    task.add_log(f"并发评估完成，成功评估 {len(task.evaluations)}/{total} 篇")

    # 阶段2: 生成综合评估
    task.stage = "正在生成综合评估..."
    task.stage_short = "综合评估"
    task.progress = 85
    task.push_progress()
    task.add_log("开始生成综合评估报告...")

    try:
        loop = asyncio.get_event_loop()
        task.comprehensive_eval = await loop.run_in_executor(
            None, evaluator.generate_comprehensive_evaluation,
            task.paper, task.evaluations
        )
        task.add_log("综合评估生成完成", "success")
    except Exception as e:
        task.add_log(f"综合评估生成失败: {e}", "error")
        task.comprehensive_eval = {
            "overall_impact_score": "N/A",
            "overall_summary": f"综合评估生成失败: {str(e)}",
            "key_findings": [],
            "citation_quality_distribution": {},
            "depth_distribution": {},
            "sentiment_distribution": {},
            "influence_areas": [],
            "notable_citations": []
        }

    # 阶段3: 学者画像与高级分析
    task.stage = "正在补全学者画像..."
    task.stage_short = "学者画像"
    task.progress = 88
    task.push_progress()
    task.add_log("开始学者画像与高级分析...")

    try:
        loop = asyncio.get_event_loop()

        def _scholar_progress(current, total, name=""):
            task.scholar_current = current
            task.scholar_total = total
            task.scholar_name = name
            task.stage = f"学者画像 {current}/{total}"
            task.push_progress()

        enricher = ScholarEnricher(log_callback=lambda msg: task.add_log(msg))
        scholar_data = await loop.run_in_executor(
            None, enricher.enrich_citations,
            task.paper, task.evaluations, task.selected_citations,
            _scholar_progress
        )
        task.scholar_profiles = scholar_data.get("scholar_profiles", [])
        task.add_log(f"学者画像完成: {len(task.scholar_profiles)} 位知名学者", "success")
    except Exception as e:
        task.add_log(f"学者画像补全失败: {e}", "error")
        logger.exception("Scholar enrichment failed")
        scholar_data = {"enriched_citations": [], "scholar_profiles": [], "self_citation_count": 0}
        task.scholar_profiles = []

    task.stage = "正在生成高级分析..."
    task.stage_short = "高级分析"
    task.progress = 91
    task.push_progress()

    try:
        analytics = AdvancedAnalytics(log_callback=lambda msg: task.add_log(msg))
        task.advanced_analytics = await loop.run_in_executor(
            None, analytics.run_full_analysis,
            task.paper, task.evaluations, scholar_data, task.comprehensive_eval
        )
        task.add_log("高级分析完成", "success")
    except Exception as e:
        task.add_log(f"高级分析失败: {e}", "error")
        logger.exception("Advanced analytics failed")
        task.advanced_analytics = {}

    # 阶段4: 生成图表
    task.stage = "正在生成图表..."
    task.stage_short = "生成图表"
    task.progress = 93
    task.push_progress()

    try:
        chart_gen = ChartGenerator(output_dir=CHARTS_DIR)
        if task.advanced_analytics:
            task.chart_assets = await loop.run_in_executor(
                None, chart_gen.generate_all, task.advanced_analytics, task.task_id
            )
            task.add_log(f"图表生成完成: {len(task.chart_assets)} 张", "success")
        else:
            task.chart_assets = {}
    except Exception as e:
        task.add_log(f"图表生成失败: {e}", "error")
        task.chart_assets = {}

    # 阶段5: 生成报告
    task.stage = "正在生成报告文件..."
    task.stage_short = "生成报告"
    task.progress = 95
    task.push_progress()
    task.add_log("开始生成MD和PDF报告...")

    try:
        report_gen = ReportGenerator(reports_dir=REPORTS_DIR)
        loop = asyncio.get_event_loop()
        task.report_paths = await loop.run_in_executor(
            None, report_gen.generate_report,
            task.paper, task.comprehensive_eval, task.evaluations, task.task_id,
            task.advanced_analytics, task.scholar_profiles, task.chart_assets
        )
        task.add_log(f"报告生成完成: {task.report_paths.get('md_filename')}", "success")
    except Exception as e:
        task.add_log(f"报告生成失败: {e}", "error")
        task.report_paths = {}

    # 完成
    task.progress = 100
    task.status = "completed"
    task.stage = "分析完成"
    task.stage_short = "完成"
    task.add_log(
        f"评估完成! 共分析 {task.analyzed} 篇论文, LLM search 成功 {task.search_llm_count} 篇, 全文 {task.fulltext_count} 篇, 仅摘要 {task.abstract_count} 篇",
        "success"
    )
    task.push_completed()


# ===== 启动 =====
if __name__ == '__main__':
    port = int(APP_SETTINGS.get("port", 5000))
    logger.info(f"Starting Citation Quality Analyzer on port {port}")
    logger.info(f"Concurrency limit: {CONCURRENCY_LIMIT}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
