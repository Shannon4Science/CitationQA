"""
后端图表生成模块
使用 matplotlib 生成分析图表 PNG，供前端展示与 Markdown/PDF 报告嵌入。
"""

import logging
import os
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

logger = logging.getLogger("citation_analyzer.chart_generator")

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

COLOR_PRIMARY = "#e8890c"
COLOR_SECONDARY = "#f5a623"
COLOR_PALETTE = ["#e8890c", "#3b82c4", "#4caf8a", "#7c5cbf", "#c45a5a",
                 "#d4892a", "#6ba3d6", "#48bb78", "#9f7aea", "#fc8181"]
FILL_COLORS = {
    "fill-cyan": "#3b82c4",
    "fill-green": "#4caf8a",
    "fill-purple": "#7c5cbf",
    "fill-orange": "#e8890c",
}


class ChartGenerator:
    """图表生成器 — 输出 PNG 文件供前端与报告使用"""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_all(self, analytics: Dict, task_id: str) -> Dict[str, str]:
        """
        从 advanced_analytics 结果生成所有图表 PNG。
        返回 {chart_name: relative_path} 字典。
        """
        charts = {}
        prefix = task_id

        td = analytics.get("time_distribution", {})
        if td.get("labels"):
            p = self._bar_chart(
                td["labels"], td["values"],
                "引用时间分布", "年份", "引用数量",
                f"{prefix}_time_dist.png"
            )
            if p:
                charts["time_distribution"] = p

        cda = analytics.get("country_distribution_all", {})
        if cda.get("labels"):
            p = self._horizontal_bar(
                cda["labels"][:8], cda["values"][:8],
                "第一作者国家/地区分布", f"{prefix}_country_all.png"
            )
            if p:
                charts["country_distribution_all"] = p

        sld = analytics.get("scholar_level_distribution", {})
        if sld.get("labels"):
            p = self._pie_chart(
                sld["labels"], sld["values"],
                "学者层级分布", f"{prefix}_scholar_level.png"
            )
            if p:
                charts["scholar_level_distribution"] = p

        desc = analytics.get("citation_description_analysis", {})
        sd = desc.get("sentiment_distribution", {})
        if sd:
            labels = []
            values = []
            for k, v in sd.items():
                if v:
                    name_map = {"positive": "正面", "neutral": "中性", "critical": "批评"}
                    labels.append(name_map.get(k, k))
                    values.append(v)
            if labels:
                p = self._pie_chart(labels, values, "引用情感分布",
                                    f"{prefix}_sentiment.png")
                if p:
                    charts["sentiment_distribution"] = p

        cd = desc.get("citation_depth", {})
        if cd:
            labels = []
            values = []
            for k, v in cd.items():
                if v:
                    name_map = {"core_citation": "核心引用", "reference_citation": "参考引用",
                                "supplementary_citation": "补充说明"}
                    labels.append(name_map.get(k, k))
                    values.append(v)
            if labels:
                p = self._pie_chart(labels, values, "引用深度分布",
                                    f"{prefix}_depth.png")
                if p:
                    charts["citation_depth"] = p

        pred = analytics.get("influence_prediction", {})
        trend = pred.get("trend_data", {})
        if trend.get("labels"):
            p = self._trend_chart(trend, "引用趋势预测",
                                  f"{prefix}_trend.png")
            if p:
                charts["trend_prediction"] = p

        scores = pred.get("impact_scores", [])
        if scores:
            p = self._impact_bars(scores, "影响力维度评分",
                                  f"{prefix}_impact.png")
            if p:
                charts["impact_scores"] = p

        return charts

    def _bar_chart(self, labels, values, title, xlabel, ylabel,
                   filename) -> Optional[str]:
        try:
            fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.5), 4))
            bars = ax.bar(labels, values, color=COLOR_PRIMARY, width=0.6, edgecolor="white")
            ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
            ax.set_xlabel(xlabel, fontsize=10)
            ax.set_ylabel(ylabel, fontsize=10)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            if len(labels) > 8:
                plt.xticks(rotation=45, ha="right", fontsize=8)
            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                            str(val), ha="center", va="bottom", fontsize=8)
            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"Bar chart failed: {e}")
            return None

    def _horizontal_bar(self, labels, values, title, filename) -> Optional[str]:
        try:
            fig, ax = plt.subplots(figsize=(7, max(3, len(labels) * 0.45)))
            y_pos = range(len(labels))
            bars = ax.barh(y_pos, values, color=COLOR_PALETTE[:len(labels)],
                          height=0.6, edgecolor="white")
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=10)
            ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.invert_yaxis()
            for bar, val in zip(bars, values):
                ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                        str(val), ha="left", va="center", fontsize=9)
            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"H-bar chart failed: {e}")
            return None

    def _pie_chart(self, labels, values, title, filename) -> Optional[str]:
        try:
            fig, ax = plt.subplots(figsize=(6, 5))
            colors = COLOR_PALETTE[:len(labels)]
            wedges, texts, autotexts = ax.pie(
                values, labels=labels, colors=colors,
                autopct="%1.0f%%", startangle=90,
                textprops={"fontsize": 10}
            )
            for at in autotexts:
                at.set_fontsize(9)
            ax.set_title(title, fontsize=14, fontweight="bold", pad=16)
            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"Pie chart failed: {e}")
            return None

    def _trend_chart(self, trend_data: Dict, title: str,
                     filename: str) -> Optional[str]:
        try:
            labels = trend_data.get("labels", [])
            actual = trend_data.get("actual", [])
            forecast = trend_data.get("forecast", [])
            fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.6), 4))

            actual_x, actual_y = [], []
            forecast_x, forecast_y = [], []
            for i, lbl in enumerate(labels):
                a = actual[i] if i < len(actual) else None
                f = forecast[i] if i < len(forecast) else None
                if a is not None:
                    actual_x.append(lbl)
                    actual_y.append(a)
                if f is not None:
                    forecast_x.append(lbl)
                    forecast_y.append(f)

            if actual_x:
                ax.plot(actual_x, actual_y, "o-", color=COLOR_PRIMARY,
                       linewidth=2, markersize=5, label="实际引用")
            if forecast_x:
                ax.plot(forecast_x, forecast_y, "s--", color="#3b82c4",
                       linewidth=2, markersize=5, label="预测引用")

            ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
            ax.set_xlabel("年份", fontsize=10)
            ax.set_ylabel("引用数量", fontsize=10)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.legend(fontsize=9)
            if len(labels) > 8:
                plt.xticks(rotation=45, ha="right", fontsize=8)
            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"Trend chart failed: {e}")
            return None

    def _impact_bars(self, scores: List[Dict], title: str,
                     filename: str) -> Optional[str]:
        try:
            labels = [s.get("label", "") for s in scores]
            vals = [s.get("score", 0) for s in scores]
            colors = [FILL_COLORS.get(s.get("color_class", ""), COLOR_PRIMARY) for s in scores]

            fig, ax = plt.subplots(figsize=(7, max(3, len(labels) * 0.5)))
            y_pos = range(len(labels))
            bars = ax.barh(y_pos, vals, color=colors, height=0.5, edgecolor="white")
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=10)
            ax.set_xlim(0, 100)
            ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.invert_yaxis()
            for bar, val in zip(bars, vals):
                ax.text(val + 1, bar.get_y() + bar.get_height() / 2,
                        f"{val}", ha="left", va="center", fontsize=10, fontweight="bold")
            plt.tight_layout()
            path = os.path.join(self.output_dir, filename)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"Impact bars failed: {e}")
            return None
