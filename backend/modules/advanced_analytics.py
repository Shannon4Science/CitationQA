"""
高级分析模块
将 CitationClaw 的统计、预测、洞察分析能力迁移为主系统可用的纯后端逻辑。
"""

import json
import logging
import math
import re
from collections import Counter
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.modules.search_llm_client import SearchLLMClient

logger = logging.getLogger("citation_analyzer.advanced_analytics")

LEVEL_LABELS = {
    "two_academy_member": "两院院士",
    "fellow": "Fellow",
    "other_academy": "其他院士",
    "distinguished": "杰青/长江/优青",
    "industry_leader": "业界领袖",
    "none": "",
}


class AdvancedAnalytics:
    """高级分析引擎 — 时间/地域/学者层级统计、被引描述深度分析、影响力预测、数据洞察"""

    def __init__(self, log_callback: Optional[Callable] = None):
        self.search_client = SearchLLMClient()
        self.log = log_callback or logger.info

    def _llm(self, prompt: str) -> str:
        return self.search_client.search_query(prompt)

    def _llm_json(self, prompt: str) -> Optional[Any]:
        return self.search_client.search_json(prompt)

    def run_full_analysis(self, target_paper: Dict, evaluations: List[Dict],
                          scholar_data: Dict,
                          comprehensive_eval: Dict) -> Dict:
        self.log("开始高级分析（引用分布 / 学者层级 / 影响力预测 / 洞察）...")

        enriched = scholar_data.get("enriched_citations", [])
        scholars = scholar_data.get("scholar_profiles", [])

        stats = self._compute_stats(evaluations, enriched, scholars)
        citation_desc_analysis = self._analyze_citation_descriptions(evaluations)
        prediction = self._generate_prediction(evaluations, stats)
        insights = self._generate_insights(stats, citation_desc_analysis, comprehensive_eval)
        citation_summary = self._summarize_citation_descriptions(evaluations)

        result = {
            "time_distribution": {
                "labels": [str(y) for y in stats["all_years"]],
                "values": [stats["year_counter"].get(y, 0) for y in stats["all_years"]],
            },
            "country_distribution_all": self._counter_to_chart(stats["country_counter_all"]),
            "country_distribution_renowned": self._counter_to_chart(stats["country_counter_renowned"]),
            "country_distribution_top": self._counter_to_chart(stats["country_counter_top"]),
            "scholar_level_distribution": self._counter_to_chart(stats["level_counter"]),
            "citation_description_analysis": citation_desc_analysis,
            "influence_prediction": prediction,
            "insight_cards": insights,
            "citation_description_summary": citation_summary,
            "stats_summary": {
                "total_papers": stats["total_papers"],
                "unique_scholars": stats["unique_scholars"],
                "fellow_count": stats["fellow_count"],
                "country_count": stats["country_count"],
                "self_citation_count": scholar_data.get("self_citation_count", 0),
                "max_citation": stats["max_cit"],
                "total_citation_sum": stats["total_cit"],
            },
        }
        self.log("高级分析完成")
        return result

    def _compute_stats(self, evaluations: List[Dict], enriched: List[Dict],
                       scholars: List[Dict]) -> Dict:
        def _norm_scholar_name(name: str) -> str:
            clean = re.sub(r'\s*[\(（][^\)）]*[\)）]', '', (name or "")).strip()
            zh = re.sub(r'[^\u4e00-\u9fff]', '', clean)
            if len(zh) >= 2:
                return zh
            en = re.sub(r'[^a-zA-Z]', '', clean).lower()
            if len(en) >= 4:
                return en
            return clean.lower()

        year_counter = Counter()
        country_counter_all = Counter()
        for i, ev in enumerate(evaluations):
            year = ev.get("citing_year")
            if year is not None:
                try:
                    y = int(year)
                    if 1900 < y < 2100:
                        year_counter[y] += 1
                except (ValueError, TypeError):
                    pass
            if i < len(enriched):
                c = enriched[i].get("first_author_country", "")
                if c and c.strip() and c.lower() not in ("", "nan", "none"):
                    country_counter_all[c.strip()] += 1

        all_years = sorted(year_counter.keys()) if year_counter else []

        country_counter_renowned = Counter()
        country_counter_top = Counter()
        level_counter = Counter()
        seen_names = set()
        for s in scholars:
            name = _norm_scholar_name(s.get("name", ""))
            if name in seen_names:
                continue
            seen_names.add(name)
            c = s.get("country", "")
            if c and c.strip():
                country_counter_renowned[c.strip()] += 1
            if s.get("is_top"):
                if c and c.strip():
                    country_counter_top[c.strip()] += 1
            level = s.get("level", "none")
            label = LEVEL_LABELS.get(level, level)
            if label:
                level_counter[label] += 1

        scholar_citations = [ev.get("scholar_citation_count", 0) or 0 for ev in evaluations]
        max_cit = max(scholar_citations) if scholar_citations else 0
        total_cit = sum(scholar_citations)

        return {
            "year_counter": dict(year_counter),
            "all_years": all_years,
            "country_counter_all": country_counter_all,
            "country_counter_renowned": country_counter_renowned,
            "country_counter_top": country_counter_top,
            "level_counter": level_counter,
            "total_papers": len(evaluations),
            "unique_scholars": len(seen_names),
            "fellow_count": sum(1 for s in scholars if s.get("is_top")),
            "country_count": len(country_counter_all),
            "max_cit": max_cit,
            "total_cit": total_cit,
        }

    def _analyze_citation_descriptions(self, evaluations: List[Dict]) -> Dict:
        self.log("  → 分析引用描述...")
        descs = []
        for ev in evaluations:
            if ev.get("fulltext_available") and ev.get("summary"):
                descs.append({
                    "title": ev.get("citing_title", ""),
                    "type": ev.get("citation_type", "unknown"),
                    "depth": ev.get("citation_depth", "unknown"),
                    "sentiment": ev.get("citation_sentiment", "unknown"),
                    "summary": ev.get("summary", ""),
                    "locations": ev.get("citation_locations", []),
                })

        if not descs:
            return self._default_citation_analysis()

        descs_text = "\n\n".join(
            f"【引用{i+1}】论文:《{d['title'][:60]}》 类型:{d['type']} 深度:{d['depth']} 态度:{d['sentiment']}\n摘要: {d['summary'][:300]}"
            for i, d in enumerate(descs[:40])
        )

        prompt = f"""以下是 {len(descs)} 篇论文对目标论文的引用分析（展示部分样本）：

{descs_text}

请对这些引用进行多维度分析，直接返回如下 JSON（不要其他文字）：

{{
  "citation_types": [
    {{"type": "类型名称", "count": 数量, "description": "简要说明"}},
    ...
  ],
  "citation_positions": [
    {{"position": "章节位置", "count": 数量}},
    ...
  ],
  "citation_themes": [
    {{"theme": "核心主题短语", "frequency": 1-10}},
    ...最多8个
  ],
  "sentiment_distribution": {{
    "positive": 正面占比(0-100),
    "neutral": 中性占比,
    "critical": 批评占比
  }},
  "key_findings": ["发现1", "发现2", "发现3"],
  "citation_depth": {{
    "core_citation": 核心引用占比(0-100),
    "reference_citation": 参考引用占比,
    "supplementary_citation": 补充说明占比
  }}
}}"""
        result = self._llm_json(prompt)
        if isinstance(result, dict) and "citation_types" in result:
            return result
        return self._default_citation_analysis()

    @staticmethod
    def _default_citation_analysis() -> Dict:
        return {
            "citation_types": [],
            "citation_positions": [],
            "citation_themes": [],
            "sentiment_distribution": {"positive": 0, "neutral": 0, "critical": 0},
            "key_findings": ["暂无足够数据进行深度分析"],
            "citation_depth": {"core_citation": 0, "reference_citation": 0, "supplementary_citation": 0},
        }

    def _generate_prediction(self, evaluations: List[Dict], stats: Dict) -> Dict:
        self.log("  → 生成影响力预测...")
        year_dist = stats["year_counter"]
        now_year = datetime.now().year

        if not year_dist:
            return self._default_prediction(now_year)

        years = sorted(year_dist.keys())
        has_now_year = year_dist.get(now_year, 0) > 0
        actual_cutoff = now_year if has_now_year else now_year - 1
        forecast_y1 = now_year
        forecast_y2 = now_year + 1

        context = f"""目标论文的引用情况数据：
- 引用论文总数：{stats['total_papers']} 篇
- 引用论文年份分布：{year_dist}
- 引用论文总被引量：{stats['total_cit']}
- 知名学者数：{stats['unique_scholars']}（其中院士/Fellow {stats['fellow_count']} 位）
- 最高单篇被引量：{stats['max_cit']}"""

        prompt = f"""{context}

当前年份为 {now_year} 年。请对该目标论文的引用趋势进行预测分析。

直接返回如下 JSON 格式（不要其他文字）：
{{
  "trend_data": {{
    "labels": ["年份1", ...],
    "actual": [实际值或null, ...],
    "forecast": [null或预测值, ...]
  }},
  "prediction_metrics": [
    {{"label": "预计{forecast_y1}年引用量", "value": "~XXX", "note": "简短说明"}},
    {{"label": "预计{forecast_y2}年引用量", "value": "~XXX", "note": "简短说明"}},
    {{"label": "引用年增速 (YoY)", "value": "+XX%", "note": "说明"}}
  ],
  "impact_scores": [
    {{"label": "维度1", "score": 0-100, "color_class": "fill-cyan"}},
    {{"label": "维度2", "score": 0-100, "color_class": "fill-green"}},
    {{"label": "维度3", "score": 0-100, "color_class": "fill-purple"}},
    {{"label": "维度4", "score": 0-100, "color_class": "fill-orange"}}
  ],
  "prediction_commentary": "预测评语（中文，100-150字）"
}}

要求：
- trend_data labels 从最早年份到 {forecast_y2}
- actual 填实际数据年份，forecast 填预测年份
- impact_scores 维度标签根据论文领域自定"""

        result = self._llm_json(prompt)
        if isinstance(result, dict) and "trend_data" in result:
            return result
        return self._fallback_prediction(stats, now_year)

    def _fallback_prediction(self, stats: Dict, now_year: int) -> Dict:
        year_counter = stats["year_counter"]
        years = sorted(year_counter.keys())
        if not years:
            return self._default_prediction(now_year)

        hist = [year_counter.get(y, 0) for y in years]
        n = len(years)
        has_now = year_counter.get(now_year, 0) > 0

        if n >= 2:
            xv = list(range(n))
            mx = sum(xv) / n
            my = sum(hist) / n
            denom = sum((xi - mx) ** 2 for xi in xv) or 1.0
            slope = sum((xi - mx) * (yi - my) for xi, yi in zip(xv, hist)) / denom
            intercept = my - slope * mx
            next1 = max(0, round(slope * n + intercept))
            next2 = max(0, round(slope * (n + 1) + intercept))
            yoy = round(100 * (hist[-1] - hist[-2]) / max(hist[-2], 1)) if hist[-2] > 0 else 0
        else:
            next1 = hist[0] if hist else 0
            next2 = next1
            yoy = 0
            slope = 0

        min_y = years[0]
        labels = [str(y) for y in range(min_y, now_year + 2)]
        actual, forecast = [], []
        for y in range(min_y, now_year + 2):
            if y < now_year:
                actual.append(year_counter.get(y, 0))
                forecast.append(None)
            elif y == now_year:
                actual.append(year_counter.get(y, 0) if has_now else None)
                forecast.append(next1)
            else:
                actual.append(None)
                forecast.append(next2)

        return {
            "trend_data": {"labels": labels, "actual": actual, "forecast": forecast},
            "prediction_metrics": [
                {"label": f"预计{now_year}年引用量", "value": f"~{next1}", "note": "趋势外推"},
                {"label": f"预计{now_year+1}年引用量", "value": f"~{next2}", "note": "趋势外推"},
                {"label": "引用年增速", "value": f"{'+' if yoy >= 0 else ''}{yoy}%", "note": "近两年数据"},
            ],
            "impact_scores": [
                {"label": "理论创新影响力", "score": min(78, max(30, 45 + stats.get("fellow_count", 0) * 3)), "color_class": "fill-cyan"},
                {"label": "跨学科扩散潜力", "score": min(72, max(25, 35 + stats.get("total_papers", 0) // 8)), "color_class": "fill-green"},
                {"label": "政策实践参考价值", "score": min(68, max(20, 30 + stats.get("country_count", 0) * 4)), "color_class": "fill-purple"},
                {"label": "国际学界认可度", "score": min(70, max(25, 32 + stats.get("unique_scholars", 0) // 4)), "color_class": "fill-orange"},
            ],
            "prediction_commentary": f"基于历史引用数据分析，该论文年均引用增量约 {round(slope, 1)} 篇，共 {stats['total_papers']} 篇施引文献。",
        }

    @staticmethod
    def _default_prediction(now_year: int) -> Dict:
        return {
            "trend_data": {"labels": [str(now_year)], "actual": [0], "forecast": [0]},
            "prediction_metrics": [],
            "impact_scores": [],
            "prediction_commentary": "数据不足，无法进行预测。",
        }

    def _generate_insights(self, stats: Dict, citation_analysis: Dict,
                           comprehensive_eval: Dict) -> List[Dict]:
        self.log("  → 生成数据洞察...")
        year_dist = stats["year_counter"]
        country_top5 = dict(stats["country_counter_all"].most_common(5))
        key_findings = citation_analysis.get("key_findings", [])
        now_year = datetime.now().year

        prompt = f"""基于以下学术引用数据，生成4条专业、精炼的数据洞察。

数据概况：
- 引用论文年份分布：{year_dist}
- 引用学者来源国家（前5）：{country_top5}
- 总知名学者数：{stats['unique_scholars']}（其中院士/Fellow {stats['fellow_count']}人）
- 引用描述发现：{key_findings}
- 引用论文最高被引量：{stats['max_cit']}

直接返回 JSON 数组：
[
  {{"color": "teal", "icon": "📈", "title": "洞察标题", "body": "洞察正文（80-120字，含数据）"}},
  {{"color": "sage", "icon": "🌏", "title": "...", "body": "..."}},
  {{"color": "amber", "icon": "🏆", "title": "...", "body": "..."}},
  {{"color": "violet", "icon": "🔬", "title": "...", "body": "..."}}
]"""
        result = self._llm_json(prompt)
        if isinstance(result, list) and len(result) >= 4:
            return result[:4]

        top_year = max(year_dist, key=year_dist.get) if year_dist else now_year
        top_n = year_dist.get(top_year, 0)
        return [
            {"color": "teal", "icon": "📈", "title": "引用时间趋势",
             "body": f"共 {stats['total_papers']} 篇引用论文，{top_year} 年发表最多（{top_n} 篇）。"},
            {"color": "sage", "icon": "🌏", "title": "地域分布",
             "body": f"引用覆盖 {stats['country_count']} 个国家/地区。"},
            {"color": "amber", "icon": "🏆", "title": "学者层次",
             "body": f"含 {stats['fellow_count']} 位院士/Fellow，{stats['unique_scholars']} 位知名学者。"},
            {"color": "violet", "icon": "🔬", "title": "引用方式",
             "body": "引用者主要将该论文作为理论依据或背景综述引用。"},
        ]

    def _summarize_citation_descriptions(self, evaluations: List[Dict]) -> str:
        self.log("  → 生成被引描述综合总结...")
        samples = [ev for ev in evaluations if ev.get("fulltext_available") and ev.get("summary")]
        if not samples:
            return ""

        descs_text = "\n\n".join(
            f"【引用{i+1}】论文：《{s['citing_title'][:80]}》\n"
            f"引用类型：{s.get('citation_type', 'unknown')} 深度：{s.get('citation_depth', 'unknown')}\n"
            f"摘要评价：{s.get('summary', '')[:400]}"
            for i, s in enumerate(samples[:50])
        )

        prompt = f"""以下是共 {len(samples)} 篇论文对目标论文的引用分析（展示 {min(50, len(samples))} 条样本）：

{descs_text}

请撰写一份引用描述综合分析文档，使用以下 Markdown 结构：

## 引用规模与分布
（2-3句话，说明引用总数、涉及领域）

## 主要引用用途
（描述引用者如何使用该论文，举例说明）

## 代表性引用描述原文
（用 > 引用块引用3-4条代表性描述）

## 综合说明
（2-3句话归纳引用模式）

全程中文，300-500字，语言简洁中性。直接输出Markdown。"""
        result = self._llm(prompt).strip()
        return result if result else ""

    @staticmethod
    def _counter_to_chart(counter: Counter, top_n: int = 10) -> Dict:
        if not counter:
            return {"labels": [], "values": []}
        items = counter.most_common(top_n)
        return {
            "labels": [item[0] for item in items],
            "values": [item[1] for item in items],
        }
