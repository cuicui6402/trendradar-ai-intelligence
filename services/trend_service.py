"""
services/trend_service.py
趋势分析服务。
对评分后的数据进行聚合、排序和趋势判断。
"""

import logging
from typing import List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


class TrendService:
    """
    将评分后的数据聚合为趋势分析结果。
    """

    def analyze(self, scored_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        对评分后的数据进行趋势分析。

        Args:
            scored_items: 已计算 trend_score 的数据条目列表

        Returns:
            趋势分析结果字典，包含：
            - summary: 总体趋势判断
            - top_items: 评分最高的条目
            - source_distribution: 来源分布统计
            - daily_trend: 每日趋势数据
        """
        if not scored_items:
            return {
                "summary": "暂无数据",
                "top_items": [],
                "source_distribution": {},
                "daily_trend": [],
            }

        df = pd.DataFrame(scored_items)

        # 按评分降序排列，取 Top 10
        top_items = (
            df.nlargest(10, "trend_score")
            .to_dict(orient="records")
        )

        # 来源分布
        source_distribution = df["source"].value_counts().to_dict()

        # 每日趋势（按日期聚合平均分）
        if "date" in df.columns:
            daily_trend = (
                df.groupby("date")["trend_score"]
                .mean()
                .reset_index()
                .sort_values("date")
                .to_dict(orient="records")
            )
        else:
            daily_trend = []

        # 总体评分
        avg_score = round(df["trend_score"].mean(), 2)
        summary = self._generate_summary(avg_score, len(scored_items))

        return {
            "summary": summary,
            "avg_score": avg_score,
            "total_items": len(scored_items),
            "top_items": top_items,
            "source_distribution": source_distribution,
            "daily_trend": daily_trend,
        }

    def _generate_summary(self, avg_score: float, item_count: int) -> str:
        """
        根据平均分和数据量生成简要趋势判断。

        Args:
            avg_score: 平均趋势评分
            item_count: 数据条目数

        Returns:
            趋势判断文本
        """
        if avg_score >= 60:
            level = "高热度"
        elif avg_score >= 35:
            level = "中等热度"
        else:
            level = "低热度"

        return f"该技术近期在 GitHub 和 Hacker News 上呈现【{level}】趋势（基于 {item_count} 条数据，平均评分 {avg_score}）。"
