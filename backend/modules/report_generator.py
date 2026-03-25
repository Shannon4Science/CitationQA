"""
报告生成模块 v4.0
生成Markdown和PDF格式的被引质量评估报告
跨平台PDF生成：使用fpdf2（纯Python，Windows/Mac/Linux通用）
"""

import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("citation_analyzer.report")

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


class ReportGenerator:
    """报告生成器 v4.0"""

    def __init__(self, reports_dir: str = None):
        self.reports_dir = reports_dir or REPORTS_DIR
        os.makedirs(self.reports_dir, exist_ok=True)

    def generate_report(self, target_paper: Dict, comprehensive_eval: Dict,
                       evaluations: List[Dict], task_id: str,
                       advanced_analytics: Optional[Dict] = None,
                       scholar_profiles: Optional[List] = None,
                       chart_assets: Optional[Dict] = None) -> Dict:
        """
        生成完整的评估报告
        Returns: {"md_path": str, "pdf_path": str}
        """
        logger.info(f"[Report] 开始生成报告: {target_paper.get('title', 'N/A')[:60]}")

        safe_title = self._safe_filename(target_paper.get("title", "report"))

        local_charts = {}
        if chart_assets:
            charts_subdir = os.path.join(self.reports_dir, f"{task_id}_charts")
            os.makedirs(charts_subdir, exist_ok=True)
            import shutil
            for name, src_path in chart_assets.items():
                if os.path.exists(src_path):
                    fname = os.path.basename(src_path)
                    dst = os.path.join(charts_subdir, fname)
                    shutil.copy2(src_path, dst)
                    local_charts[name] = {
                        "abs": dst,
                        "rel": f"{task_id}_charts/{fname}",
                    }

        md_content = self._build_markdown(target_paper, comprehensive_eval, evaluations)

        if advanced_analytics or scholar_profiles:
            md_chart_refs = {k: v["rel"] for k, v in local_charts.items()}
            md_content += self._build_advanced_markdown(
                advanced_analytics or {}, scholar_profiles or [], md_chart_refs
            )

        md_filename = f"{task_id}_{safe_title}.md"
        md_path = os.path.join(self.reports_dir, md_filename)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"[Report] MD报告已保存: {md_path}")

        pdf_filename = f"{task_id}_{safe_title}.pdf"
        pdf_path = os.path.join(self.reports_dir, pdf_filename)

        pdf_chart_refs = {k: v["abs"] for k, v in local_charts.items()}
        try:
            self._generate_pdf(target_paper, comprehensive_eval, evaluations, pdf_path,
                              advanced_analytics, scholar_profiles, pdf_chart_refs)
        except Exception as e:
            logger.error(f"[Report] PDF生成异常: {e}")

        if not os.path.exists(pdf_path):
            logger.warning("[Report] fpdf2 PDF不存在，尝试weasyprint回退")
            self._fallback_pdf(target_paper, comprehensive_eval, evaluations, pdf_path)

        return {
            "md_path": md_path,
            "pdf_path": pdf_path if os.path.exists(pdf_path) else md_path,
            "md_filename": md_filename,
            "pdf_filename": pdf_filename if os.path.exists(pdf_path) else md_filename
        }

    def _build_markdown(self, target_paper: Dict, comprehensive_eval: Dict,
                       evaluations: List[Dict]) -> str:
        """构建Markdown报告内容"""
        lines = []

        title = target_paper.get("title", "未知论文")
        lines.append(f"# 论文被引质量评估报告")
        lines.append(f"")
        lines.append(f"> **被评估论文**: {title}")
        lines.append(f"> **报告作者**: 党琛颢（Chenhao Dang）")
        lines.append(f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> **生成工具**: Citation Quality Analyzer")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

        # 第一部分：被评估论文概述
        lines.append(f"## 1. 被评估论文概述")
        lines.append(f"")
        lines.append(f"### 基本信息")
        lines.append(f"")
        lines.append(f"| 项目 | 内容 |")
        lines.append(f"|------|------|")
        lines.append(f"| **标题** | {title} |")
        lines.append(f"| **年份** | {target_paper.get('year', 'N/A')} |")
        lines.append(f"| **发表场所** | {target_paper.get('venue', 'N/A') or 'N/A'} |")
        lines.append(f"| **5源去重后总被引次数** | {target_paper.get('citation_count', 0)} |")
        raw_count = target_paper.get("raw_citation_count", 0)
        if raw_count and raw_count != target_paper.get("citation_count", 0):
            lines.append(f"| **源接口参考被引数** | {raw_count} |")
        lines.append(f"| **有影响力的被引** | {target_paper.get('influential_citation_count', 0)} |")

        arxiv_id = target_paper.get("arxiv_id")
        if arxiv_id:
            lines.append(f"| **ArXiv ID** | [{arxiv_id}](https://arxiv.org/abs/{arxiv_id}) |")

        doi = target_paper.get("doi")
        if doi:
            lines.append(f"| **DOI** | [{doi}](https://doi.org/{doi}) |")

        lines.append(f"")

        authors = target_paper.get("authors", [])
        if authors:
            lines.append(f"### 作者信息")
            lines.append(f"")
            for i, author in enumerate(authors):
                name = author.get("name", "N/A")
                affil = author.get("affiliation", "")
                if affil:
                    lines.append(f"{i+1}. **{name}** - {affil}")
                else:
                    lines.append(f"{i+1}. **{name}**")
            lines.append(f"")

        abstract = target_paper.get("abstract", "")
        if abstract:
            lines.append(f"### 论文摘要")
            lines.append(f"")
            lines.append(f"{abstract}")
            lines.append(f"")

        lines.append(f"---")
        lines.append(f"")

        # 第二部分：综合评估总结
        lines.append(f"## 2. 综合评估总结")
        lines.append(f"")

        overall_score = comprehensive_eval.get("overall_impact_score", "N/A")
        lines.append(f"### 总体影响力评分: {overall_score}/10")
        lines.append(f"")

        overall_summary = comprehensive_eval.get("overall_summary", "")
        if overall_summary:
            lines.append(f"### 总结")
            lines.append(f"")
            lines.append(f"{overall_summary}")
            lines.append(f"")

        key_findings = comprehensive_eval.get("key_findings", [])
        if key_findings:
            lines.append(f"### 关键发现")
            lines.append(f"")
            for finding in key_findings:
                lines.append(f"- {finding}")
            lines.append(f"")

        type_dist = comprehensive_eval.get("citation_quality_distribution", {})
        if type_dist:
            lines.append(f"### 引用类型分布")
            lines.append(f"")
            lines.append(f"| 引用类型 | 数量 |")
            lines.append(f"|----------|------|")
            type_names = {
                "background_mention": "背景提及",
                "related_work_brief": "相关工作简要提及",
                "method_reference": "方法重点参考",
                "experiment_comparison": "实验对比/Benchmark",
                "multiple_deep": "多处深入引用",
                "unknown": "无法判断"
            }
            for key, name in type_names.items():
                count = type_dist.get(key, 0)
                if count:
                    lines.append(f"| {name} | {count} |")
            lines.append(f"")

        depth_dist = comprehensive_eval.get("depth_distribution", {})
        if depth_dist:
            lines.append(f"### 引用深度分布")
            lines.append(f"")
            lines.append(f"| 深度级别 | 数量 |")
            lines.append(f"|----------|------|")
            depth_names = {
                "superficial": "表面引用",
                "moderate": "中等深度",
                "substantial": "深入引用",
                "unknown": "无法判断"
            }
            for key, name in depth_names.items():
                count = depth_dist.get(key, 0)
                if count:
                    lines.append(f"| {name} | {count} |")
            lines.append(f"")

        influence_areas = comprehensive_eval.get("influence_areas", [])
        if influence_areas:
            lines.append(f"### 主要影响领域")
            lines.append(f"")
            for area in influence_areas:
                lines.append(f"- {area}")
            lines.append(f"")

        lines.append(f"---")
        lines.append(f"")

        # 第三部分：被引论文列表
        lines.append(f"## 3. 被引论文列表")
        lines.append(f"")
        lines.append(f"共分析了 **{len(evaluations)}** 篇被引论文。")
        lines.append(f"")

        fulltext_count = sum(1 for e in evaluations if e.get("fulltext_available", False))
        abstract_count = len(evaluations) - fulltext_count
        lines.append(f"- 获取全文分析: **{fulltext_count}** 篇")
        lines.append(f"- 仅摘要分析: **{abstract_count}** 篇")
        lines.append(f"")

        lines.append(f"| 序号 | 论文标题 | 年份 | 引用类型 | 质量评分 | 论文影响力 | GS被引 | 来源判断 | 全文 |")
        lines.append(f"|------|----------|------|----------|----------|------------|--------|----------|------|")

        for i, ev in enumerate(evaluations):
            ct = ev.get("citation_type", "unknown")
            score = ev.get("quality_score", 0)
            ft = "是" if ev.get("fulltext_available", False) else "否"
            year = ev.get("citing_year", "N/A")
            influence = ev.get("paper_influence_score", 0)
            scholar_cites = ev.get("scholar_citation_count", 0)
            source = ev.get("publication_source", "N/A")
            t = ev.get("citing_title", "N/A")
            if len(str(t)) > 60:
                t = str(t)[:57] + "..."
            if len(str(source)) > 18:
                source = str(source)[:15] + "..."
            lines.append(f"| {i+1} | {t} | {year} | {ct} | {score}/5 | {influence}/10 | {scholar_cites} | {source} | {ft} |")

        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

        # 第四部分：详细评估内容
        lines.append(f"## 4. 详细评估内容")
        lines.append(f"")

        for i, ev in enumerate(evaluations):
            lines.append(f"### 4.{i+1} {ev.get('citing_title', 'N/A')}")
            lines.append(f"")

            lines.append(f"| 项目 | 内容 |")
            lines.append(f"|------|------|")
            lines.append(f"| **年份** | {ev.get('citing_year', 'N/A')} |")
            lines.append(f"| **引用类型** | {ev.get('citation_type', 'unknown')} |")
            lines.append(f"| **引用深度** | {ev.get('citation_depth', 'unknown')} |")
            lines.append(f"| **引用态度** | {ev.get('citation_sentiment', 'unknown')} |")
            lines.append(f"| **质量评分** | {ev.get('quality_score', 0)}/5 |")
            lines.append(f"| **评估方式** | {ev.get('evaluation_method', 'unknown')} |")
            lines.append(f"| **联网证据源数** | {len(ev.get('evidence_sources', []) or [])} |")
            lines.append(f"| **论文影响力评分** | {ev.get('paper_influence_score', 0)}/10 ({ev.get('paper_influence_level', '未知')}) |")
            lines.append(f"| **Google Scholar被引** | {ev.get('scholar_citation_count', 0)} |")
            lines.append(f"| **发表来源判断** | {ev.get('publication_source', 'N/A')} |")
            lines.append(f"| **来源类型** | {ev.get('publication_source_type', 'N/A')} |")
            lines.append(f"| **全文获取** | {'是' if ev.get('fulltext_available', False) else '否'} |")
            lines.append(f"| **内容来源** | {ev.get('content_type', 'N/A')} |")
            lines.append(f"")

            influence_reason = ev.get("paper_influence_reason", "")
            if influence_reason:
                lines.append(f"**论文影响力说明**: {influence_reason}")
                lines.append(f"")

            summary = ev.get("summary", "")
            if summary:
                lines.append(f"**摘要评价**: {summary}")
                lines.append(f"")

            detailed = ev.get("detailed_analysis", "")
            if detailed:
                lines.append(f"**详细分析**: {detailed}")
                lines.append(f"")

            evidence_summary = ev.get("evidence_summary", "")
            if evidence_summary:
                lines.append(f"**联网核验说明**: {evidence_summary}")
                lines.append(f"")

            locations = ev.get("citation_locations", [])
            if locations:
                lines.append(f"**引用位置**:")
                lines.append(f"")
                for loc in locations:
                    section = loc.get("section", "N/A")
                    context = loc.get("context", "N/A")
                    purpose = loc.get("purpose", "N/A")
                    lines.append(f"- **{section}**: {context}")
                    lines.append(f"  - 目的: {purpose}")
                lines.append(f"")

            lines.append(f"---")
            lines.append(f"")

        lines.append(f"")
        lines.append(f"*本报告由 Citation Quality Analyzer 自动生成*")
        lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    def _build_advanced_markdown(self, analytics: Dict, scholars: List,
                                chart_assets: Dict) -> str:
        """构建高级分析 Markdown 段落（追加到基础报告之后）"""
        lines = ["\n---\n", "## 5. 高级分析", ""]

        stats = analytics.get("stats_summary", {})
        if stats:
            lines.append("### 分析概况")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 施引论文总数 | {stats.get('total_papers', 0)} |")
            lines.append(f"| 知名学者数 | {stats.get('unique_scholars', 0)} |")
            lines.append(f"| 院士/Fellow数 | {stats.get('fellow_count', 0)} |")
            lines.append(f"| 覆盖国家/地区 | {stats.get('country_count', 0)} |")
            lines.append(f"| 自引论文数 | {stats.get('self_citation_count', 0)} |")
            lines.append("")

        for chart_name, chart_path in chart_assets.items():
            label = {
                "time_distribution": "引用时间分布",
                "country_distribution_all": "第一作者国家/地区分布",
                "scholar_level_distribution": "学者层级分布",
                "sentiment_distribution": "引用情感分布",
                "citation_depth": "引用深度分布",
                "trend_prediction": "引用趋势预测",
                "impact_scores": "影响力维度评分",
            }.get(chart_name, chart_name)
            lines.append(f"### {label}")
            lines.append("")
            lines.append(f"![{label}]({chart_path})")
            lines.append("")

        if scholars:
            lines.append("### 知名学者画像一览")
            lines.append("")
            lines.append("| 姓名 | 机构 | 国家 | 荣誉/头衔 | 层级 | 引用论文 |")
            lines.append("|------|------|------|-----------|------|----------|")
            for s in scholars[:30]:
                name = s.get("name", "")
                inst = s.get("institution", "")
                country = s.get("country", "")
                honors = s.get("honors", "") or s.get("title", "")
                level = s.get("level_label", "")
                citing = s.get("citing_paper_title", "")
                if len(citing) > 40:
                    citing = citing[:37] + "..."
                lines.append(f"| {name} | {inst} | {country} | {honors} | {level} | {citing} |")
            lines.append("")

        desc_analysis = analytics.get("citation_description_analysis", {})
        if desc_analysis.get("key_findings"):
            lines.append("### 被引描述深度分析 — 关键发现")
            lines.append("")
            for f in desc_analysis["key_findings"]:
                lines.append(f"- {f}")
            lines.append("")

        pred = analytics.get("influence_prediction", {})
        commentary = pred.get("prediction_commentary", "")
        if commentary:
            lines.append("### 影响力预测分析")
            lines.append("")
            lines.append(commentary)
            lines.append("")
            metrics = pred.get("prediction_metrics", [])
            if metrics:
                lines.append("| 指标 | 预测值 | 说明 |")
                lines.append("|------|--------|------|")
                for m in metrics:
                    lines.append(f"| {m.get('label', '')} | {m.get('value', '')} | {m.get('note', '')} |")
                lines.append("")

        insights = analytics.get("insight_cards", [])
        if insights:
            lines.append("### 数据洞察")
            lines.append("")
            for ins in insights:
                title = ins.get("title", "")
                body = ins.get("body", "")
                body_clean = re.sub(r"<[^>]+>", "", body)
                lines.append(f"**{ins.get('icon', '')} {title}**")
                lines.append(f"")
                lines.append(f"{body_clean}")
                lines.append(f"")

        summary = analytics.get("citation_description_summary", "")
        if summary:
            lines.append("### 被引描述综合总结")
            lines.append("")
            lines.append(summary)
            lines.append("")

        lines.append("")
        return "\n".join(lines)

    def _generate_pdf(self, target_paper: Dict, comprehensive_eval: Dict,
                     evaluations: List[Dict], pdf_path: str,
                     advanced_analytics: Optional[Dict] = None,
                     scholar_profiles: Optional[List] = None,
                     chart_assets: Optional[Dict] = None) -> bool:
        """
        使用fpdf2生成PDF报告（跨平台，纯Python）
        """
        try:
            from fpdf import FPDF

            class CitationPDF(FPDF):
                def __init__(self):
                    super().__init__()
                    self._setup_fonts()

                def _setup_fonts(self):
                    """设置支持中文的字体（跨平台）"""
                    # 只使用TTF格式（fpdf2不支持TTC和OTF）
                    font_paths = [
                        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                        "C:/Windows/Fonts/msyh.ttf",
                        "C:/Windows/Fonts/simhei.ttf",
                        "C:/Windows/Fonts/simsun.ttf",
                        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                    ]
                    for fp in font_paths:
                        if os.path.exists(fp):
                            try:
                                self.add_font("CJK", "", fp, uni=True)
                                self.add_font("CJK", "B", fp, uni=True)
                                return
                            except Exception:
                                continue
                    # fallback: use built-in Helvetica
                    logger.warning("[Report] 未找到中文字体，使用默认字体")

                def _use_font(self, style="", size=10):
                    try:
                        self.set_font("CJK", style, size)
                    except Exception:
                        self.set_font("Helvetica", style, size)

                def header(self):
                    self._use_font("B", 8)
                    self.set_text_color(180, 120, 40)
                    self.cell(0, 8, "Citation Quality Analyzer", align="R", new_x="LMARGIN", new_y="NEXT")
                    self.set_draw_color(220, 160, 60)
                    self.line(10, self.get_y(), 200, self.get_y())
                    self.ln(4)

                def footer(self):
                    self.set_y(-15)
                    self._use_font("", 7)
                    self.set_text_color(150, 150, 150)
                    self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

                def section_title(self, text, level=1):
                    sizes = {1: 16, 2: 13, 3: 11}
                    colors = {1: (180, 100, 20), 2: (200, 120, 30), 3: (220, 140, 40)}
                    self._use_font("B", sizes.get(level, 10))
                    self.set_text_color(*colors.get(level, (0, 0, 0)))
                    self.ln(3)
                    self.multi_cell(0, 7, self._clean(text))
                    if level <= 2:
                        self.set_draw_color(*colors.get(level, (0, 0, 0)))
                        self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
                    self.ln(3)
                    self.set_text_color(0, 0, 0)

                def body_text(self, text, bold=False):
                    self._use_font("B" if bold else "", 9)
                    self.set_text_color(50, 50, 50)
                    self.multi_cell(0, 5, self._clean(text))
                    self.ln(2)

                def key_value(self, key, value):
                    self._use_font("B", 9)
                    self.set_text_color(100, 70, 20)
                    kw = self.get_string_width(self._clean(key) + ": ") + 2
                    self.cell(kw, 5, self._clean(key) + ": ")
                    self._use_font("", 9)
                    self.set_text_color(50, 50, 50)
                    self.multi_cell(0, 5, self._clean(str(value)))
                    self.ln(1)

                def _clean(self, text):
                    if not text:
                        return ""
                    text = str(text)
                    text = text.replace('\r\n', '\n').replace('\r', '\n')
                    # Remove problematic characters
                    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
                    return text

            pdf = CitationPDF()
            pdf.alias_nb_pages()
            pdf.set_auto_page_break(auto=True, margin=20)
            pdf.add_page()

            title = target_paper.get("title", "未知论文")

            # Title page
            pdf.section_title("论文被引质量评估报告", 1)
            pdf.key_value("被评估论文", title)
            pdf.key_value("报告作者", "党琛颢（Chenhao Dang）")
            pdf.key_value("生成时间", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            pdf.key_value("生成工具", "Citation Quality Analyzer")
            pdf.ln(5)

            # Section 1: Paper overview
            pdf.section_title("1. 被评估论文概述", 2)
            pdf.key_value("标题", title)
            pdf.key_value("年份", str(target_paper.get('year', 'N/A')))
            pdf.key_value("发表场所", str(target_paper.get('venue', 'N/A') or 'N/A'))
            pdf.key_value("5源去重后总被引次数", str(target_paper.get('citation_count', 0)))
            raw_count = target_paper.get("raw_citation_count", 0)
            if raw_count and raw_count != target_paper.get("citation_count", 0):
                pdf.key_value("源接口参考被引数", str(raw_count))
            pdf.key_value("有影响力的被引", str(target_paper.get('influential_citation_count', 0)))

            if target_paper.get("arxiv_id"):
                pdf.key_value("ArXiv ID", target_paper["arxiv_id"])
            if target_paper.get("doi"):
                pdf.key_value("DOI", target_paper["doi"])

            authors = target_paper.get("authors", [])
            if authors:
                author_str = ", ".join([a.get("name", "N/A") for a in authors])
                pdf.key_value("作者", author_str)

            abstract = target_paper.get("abstract", "")
            if abstract:
                pdf.section_title("论文摘要", 3)
                pdf.body_text(abstract[:1000])

            # Section 2: Comprehensive evaluation
            pdf.add_page()
            pdf.section_title("2. 综合评估总结", 2)

            overall_score = comprehensive_eval.get("overall_impact_score", "N/A")
            pdf.section_title(f"总体影响力评分: {overall_score}/10", 3)

            overall_summary = comprehensive_eval.get("overall_summary", "")
            if overall_summary:
                pdf.body_text(overall_summary)

            key_findings = comprehensive_eval.get("key_findings", [])
            if key_findings:
                pdf.section_title("关键发现", 3)
                for finding in key_findings:
                    pdf.body_text(f"  - {finding}")

            type_dist = comprehensive_eval.get("citation_quality_distribution", {})
            if type_dist:
                pdf.section_title("引用类型分布", 3)
                type_names = {
                    "background_mention": "背景提及",
                    "related_work_brief": "相关工作简要提及",
                    "method_reference": "方法重点参考",
                    "experiment_comparison": "实验对比/Benchmark",
                    "multiple_deep": "多处深入引用",
                    "unknown": "无法判断"
                }
                for key, name in type_names.items():
                    count = type_dist.get(key, 0)
                    if count:
                        pdf.key_value(name, str(count))

            depth_dist = comprehensive_eval.get("depth_distribution", {})
            if depth_dist:
                pdf.section_title("引用深度分布", 3)
                depth_names = {
                    "superficial": "表面引用",
                    "moderate": "中等深度",
                    "substantial": "深入引用",
                    "unknown": "无法判断"
                }
                for key, name in depth_names.items():
                    count = depth_dist.get(key, 0)
                    if count:
                        pdf.key_value(name, str(count))

            # Section 3: Citation list summary
            pdf.add_page()
            pdf.section_title("3. 被引论文列表", 2)
            pdf.body_text(f"共分析了 {len(evaluations)} 篇被引论文。")

            fulltext_count = sum(1 for e in evaluations if e.get("fulltext_available", False))
            abstract_count = len(evaluations) - fulltext_count
            pdf.key_value("获取全文分析", f"{fulltext_count} 篇")
            pdf.key_value("仅摘要分析", f"{abstract_count} 篇")
            pdf.ln(3)

            # Summary table
            for i, ev in enumerate(evaluations):
                t = str(ev.get("citing_title", "N/A"))
                if len(t) > 55:
                    t = t[:52] + "..."
                ct = ev.get("citation_type", "unknown")
                score = ev.get("quality_score", 0)
                influence = ev.get("paper_influence_score", 0)
                ft = "全文" if ev.get("fulltext_available", False) else "摘要"
                year = ev.get("citing_year", "N/A")

                pdf._use_font("B", 8)
                pdf.set_text_color(100, 70, 20)
                pdf.cell(8, 5, f"{i+1}.")
                pdf._use_font("", 8)
                pdf.set_text_color(50, 50, 50)
                pdf.cell(100, 5, pdf._clean(t))
                pdf.cell(15, 5, str(year))
                pdf.cell(28, 5, ct)
                pdf.cell(14, 5, f"{score}/5")
                pdf.cell(14, 5, f"{influence}/10")
                pdf.cell(15, 5, ft, new_x="LMARGIN", new_y="NEXT")

                if pdf.get_y() > 270:
                    pdf.add_page()

            # Section 4: Detailed evaluations
            pdf.add_page()
            pdf.section_title("4. 详细评估内容", 2)

            for i, ev in enumerate(evaluations):
                if pdf.get_y() > 230:
                    pdf.add_page()

                pdf.section_title(f"4.{i+1} {ev.get('citing_title', 'N/A')}", 3)
                pdf.key_value("年份", str(ev.get('citing_year', 'N/A')))
                pdf.key_value("引用类型", str(ev.get('citation_type', 'unknown')))
                pdf.key_value("引用深度", str(ev.get('citation_depth', 'unknown')))
                pdf.key_value("引用态度", str(ev.get('citation_sentiment', 'unknown')))
                pdf.key_value("质量评分", f"{ev.get('quality_score', 0)}/5")
                pdf.key_value("评估方式", str(ev.get('evaluation_method', 'unknown')))
                pdf.key_value("联网证据源数", str(len(ev.get('evidence_sources', []) or [])))
                pdf.key_value("论文影响力评分", f"{ev.get('paper_influence_score', 0)}/10 ({ev.get('paper_influence_level', '未知')})")
                pdf.key_value("Google Scholar被引", str(ev.get('scholar_citation_count', 0)))
                pdf.key_value("发表来源判断", str(ev.get('publication_source', 'N/A')))
                pdf.key_value("来源类型", str(ev.get('publication_source_type', 'N/A')))
                pdf.key_value("全文获取", '是' if ev.get('fulltext_available', False) else '否')
                pdf.key_value("内容来源", str(ev.get('content_type', 'N/A')))

                influence_reason = ev.get("paper_influence_reason", "")
                if influence_reason:
                    pdf._use_font("B", 9)
                    pdf.set_text_color(100, 70, 20)
                    pdf.cell(0, 5, "论文影响力说明:", new_x="LMARGIN", new_y="NEXT")
                    pdf.body_text(influence_reason)

                summary = ev.get("summary", "")
                if summary:
                    pdf._use_font("B", 9)
                    pdf.set_text_color(100, 70, 20)
                    pdf.cell(0, 5, "摘要评价:", new_x="LMARGIN", new_y="NEXT")
                    pdf.body_text(summary)

                detailed = ev.get("detailed_analysis", "")
                if detailed:
                    pdf._use_font("B", 9)
                    pdf.set_text_color(100, 70, 20)
                    pdf.cell(0, 5, "详细分析:", new_x="LMARGIN", new_y="NEXT")
                    pdf.body_text(detailed[:500])

                evidence_summary = ev.get("evidence_summary", "")
                if evidence_summary:
                    pdf._use_font("B", 9)
                    pdf.set_text_color(100, 70, 20)
                    pdf.cell(0, 5, "联网核验说明:", new_x="LMARGIN", new_y="NEXT")
                    pdf.body_text(evidence_summary[:300])

                locations = ev.get("citation_locations", [])
                if locations:
                    pdf._use_font("B", 9)
                    pdf.set_text_color(100, 70, 20)
                    pdf.cell(0, 5, "引用位置:", new_x="LMARGIN", new_y="NEXT")
                    for loc in locations[:3]:
                        section = loc.get("section", "N/A")
                        context = loc.get("context", "N/A")[:200]
                        pdf.body_text(f"  [{section}] {context}")

                pdf.set_draw_color(200, 200, 200)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(3)

            if advanced_analytics or scholar_profiles:
                pdf.add_page()
                pdf.section_title("5. 高级分析", 2)

                if chart_assets:
                    for chart_name, chart_path in chart_assets.items():
                        if os.path.exists(chart_path):
                            label = {
                                "time_distribution": "引用时间分布",
                                "country_distribution_all": "国家/地区分布",
                                "scholar_level_distribution": "学者层级分布",
                                "sentiment_distribution": "引用情感分布",
                                "citation_depth": "引用深度分布",
                                "trend_prediction": "引用趋势预测",
                                "impact_scores": "影响力维度评分",
                            }.get(chart_name, chart_name)
                            pdf.section_title(label, 3)
                            try:
                                img_w = min(170, pdf.epw)
                                pdf.image(chart_path, w=img_w)
                                pdf.ln(5)
                            except Exception as img_e:
                                pdf.body_text(f"(图表加载失败: {img_e})")
                            if pdf.get_y() > 240:
                                pdf.add_page()

                if scholar_profiles:
                    if pdf.get_y() > 200:
                        pdf.add_page()
                    pdf.section_title("知名学者画像一览", 3)
                    for s in (scholar_profiles or [])[:20]:
                        name = s.get("name", "")
                        inst = s.get("institution", "")
                        country = s.get("country", "")
                        honors = s.get("honors", "") or s.get("title", "")
                        level = s.get("level_label", "")
                        citing = s.get("citing_paper_title", "")
                        pdf.key_value("学者", f"{name} | {inst} | {country}")
                        if honors:
                            pdf.key_value("荣誉", honors)
                        if level:
                            pdf.key_value("层级", level)
                        if citing:
                            c_short = citing[:60] + ("..." if len(citing) > 60 else "")
                            pdf.key_value("引用论文", c_short)
                        pdf.ln(2)
                        if pdf.get_y() > 250:
                            pdf.add_page()

                if advanced_analytics:
                    pred = advanced_analytics.get("influence_prediction", {})
                    commentary = pred.get("prediction_commentary", "")
                    if commentary:
                        if pdf.get_y() > 220:
                            pdf.add_page()
                        pdf.section_title("影响力预测分析", 3)
                        pdf.body_text(commentary)

                    insights = advanced_analytics.get("insight_cards", [])
                    if insights:
                        if pdf.get_y() > 220:
                            pdf.add_page()
                        pdf.section_title("数据洞察", 3)
                        for ins in insights:
                            title_text = f"{ins.get('icon', '')} {ins.get('title', '')}"
                            body = re.sub(r"<[^>]+>", "", ins.get("body", ""))
                            pdf.body_text(f"{title_text}: {body}")

                    desc_summary = advanced_analytics.get("citation_description_summary", "")
                    if desc_summary:
                        if pdf.get_y() > 220:
                            pdf.add_page()
                        pdf.section_title("被引描述综合总结", 3)
                        pdf.body_text(desc_summary[:2000])

            pdf.output(pdf_path)
            logger.info(f"[Report] PDF生成成功: {pdf_path}")
            return True

        except Exception as e:
            logger.error(f"[Report] PDF生成失败: {e}")
            # Fallback: try weasyprint
            return self._fallback_pdf(target_paper, comprehensive_eval, evaluations, pdf_path)

    def _fallback_pdf(self, target_paper, comprehensive_eval, evaluations, pdf_path):
        """备用PDF生成方案：使用weasyprint或markdown+html"""
        try:
            import markdown
            from weasyprint import HTML

            md_content = self._build_markdown(target_paper, comprehensive_eval, evaluations)
            html_content = markdown.markdown(md_content, extensions=["tables", "fenced_code"])

            styled_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
h1 {{ color: #d4760a; border-bottom: 2px solid #d4760a; padding-bottom: 10px; }}
h2 {{ color: #e8890c; border-bottom: 1px solid #e8890c; padding-bottom: 5px; }}
h3 {{ color: #f5a623; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 0.9em; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f5a623; color: white; }}
tr:nth-child(even) {{ background-color: #fdf6e3; }}
blockquote {{ border-left: 4px solid #f5a623; padding-left: 15px; color: #666; background: #fdf6e3; margin: 10px 0; padding: 10px 15px; }}
</style></head><body>{html_content}</body></html>"""

            HTML(string=styled_html).write_pdf(pdf_path)
            logger.info(f"[Report] PDF生成成功(weasyprint): {pdf_path}")
            return True
        except Exception as e:
            logger.error(f"[Report] 备用PDF生成也失败: {e}")
            return False

    def _safe_filename(self, title: str) -> str:
        safe = re.sub(r'[^\w\s-]', '', title)[:60]
        safe = re.sub(r'\s+', '_', safe).strip('_')
        return safe or "report"


def test_report():
    """测试报告生成"""
    logging.basicConfig(level=logging.INFO)
    gen = ReportGenerator()

    target = {
        "title": "Test Paper: A Novel Approach",
        "abstract": "This paper presents a novel approach to testing.",
        "year": 2024,
        "venue": "Test Conference",
        "citation_count": 50,
        "influential_citation_count": 10,
        "arxiv_id": "2401.00001",
        "doi": "10.1234/test",
        "authors": [
            {"name": "Author One", "affiliation": "University A"},
            {"name": "Author Two", "affiliation": "Company B"}
        ]
    }

    comprehensive = {
        "overall_impact_score": 7,
        "citation_quality_distribution": {
            "background_mention": 3, "related_work_brief": 2,
            "method_reference": 1, "experiment_comparison": 1
        },
        "depth_distribution": {"superficial": 2, "moderate": 3, "substantial": 2},
        "sentiment_distribution": {"positive": 5, "neutral": 2},
        "key_findings": ["该论文在多个领域有影响", "主要被作为方法参考"],
        "overall_summary": "测试论文具有较高的学术影响力。",
        "influence_areas": ["AI", "NLP"],
        "notable_citations": ["Paper A", "Paper B"]
    }

    evaluations = [
        {
            "citing_title": "Citing Paper 1: A Deep Analysis",
            "citing_year": 2024,
            "citation_type": "method_reference",
            "citation_depth": "substantial",
            "citation_sentiment": "positive",
            "quality_score": 4,
            "summary": "深入引用了目标论文的方法",
            "detailed_analysis": "该论文在方法部分详细引用了目标论文。",
            "fulltext_available": True,
            "content_type": "html",
            "citation_locations": [
                {"section": "Method", "context": "We follow the approach of...", "purpose": "方法参考"}
            ]
        },
        {
            "citing_title": "Citing Paper 2: Brief Mention",
            "citing_year": 2025,
            "citation_type": "background_mention",
            "citation_depth": "superficial",
            "citation_sentiment": "neutral",
            "quality_score": 2,
            "summary": "仅在背景中简单提及",
            "detailed_analysis": "无法获取全文进行详细分析。",
            "fulltext_available": False,
            "content_type": "abstract_only",
            "citation_locations": []
        }
    ]

    result = gen.generate_report(target, comprehensive, evaluations, "test_001")
    print(f"MD路径: {result['md_path']}")
    print(f"PDF路径: {result['pdf_path']}")
    print(f"MD文件存在: {os.path.exists(result['md_path'])}")
    print(f"PDF文件存在: {os.path.exists(result['pdf_path'])}")


if __name__ == "__main__":
    test_report()
