"""
services/scoring_service.py
趋势评分计算服务。

提供两组评分能力：

1. DataFrame 级评分（第 4 阶段新增）：
   - normalize_series()          数值列归一化到 0-100
   - calculate_freshness_score()  时间新鲜度评分
   - score_github_repos()         GitHub 仓库趋势评分
   - score_hn_items()             Hacker News 帖子趋势评分

2. 单条评分（第 1 阶段保留，供 tests 兼容）：
   - ScoringService.calculate_score()
   - ScoringService.score_all()

GitHub trend_score 公式（v1）：
  trend_score = stars_score * 0.4
              + forks_score * 0.2
              + issues_score * 0.1
              + freshness_score * 0.3

HN trend_score 公式（v1）：
  trend_score = points_score * 0.4
              + comments_score * 0.3
              + freshness_score * 0.3
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
# 公共工具函数
# ======================================================================

def normalize_series(series: pd.Series) -> pd.Series:
    """
    将数值列归一化到 0-100。

    处理：
    - 空值 → 填充 0
    - 非数值 → 强制转换，失败填充 0
    - max == min → 全部给 50（中间值）

    Args:
        series: 待归一化的 Series

    Returns:
        归一化后的 Series（0-100）
    """
    # 强制转换为数值，无法转换的变为 NaN
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)

    s_min = s.min()
    s_max = s.max()

    if s_max == s_min:
        # 所有值相同时给中间分
        return pd.Series([50.0] * len(s), index=s.index)

    return ((s - s_min) / (s_max - s_min) * 100).round(2)


def calculate_freshness_score(date_series: pd.Series, reference_date: datetime = None) -> pd.Series:
    """
    根据时间距离当前日期的天数计算新鲜度评分。

    规则：
    - 今天：100 分
    - 7 天内：90-100 分（线性递减）
    - 30 天内：50-90 分（线性递减）
    - 90 天内：10-50 分（线性递减）
    - 超过 90 天：10 分
    - 时间解析失败：10 分

    Args:
        date_series: 日期字符串 Series（YYYY-MM-DD）
        reference_date: 参考日期，默认为当前时间

    Returns:
        新鲜度评分 Series（0-100）
    """
    if reference_date is None:
        reference_date = datetime.now()

    def _score_one(date_str):
        """计算单条日期的新鲜度评分。"""
        try:
            # 尝试解析日期（兼容 YYYY-MM-DD 和 ISO 格式）
            if isinstance(date_str, str):
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            else:
                return 10.0  # 非字符串类型
        except (ValueError, TypeError):
            return 10.0

        days_ago = max(0, (reference_date - dt).days)

        if days_ago == 0:
            return 100.0
        elif days_ago <= 7:
            # 7天内：100 → 90 线性递减
            return round(100.0 - (days_ago / 7) * 10, 2)
        elif days_ago <= 30:
            # 30天内：90 → 50 线性递减
            return round(90.0 - ((days_ago - 7) / 23) * 40, 2)
        elif days_ago <= 90:
            # 90天内：50 → 10 线性递减
            return round(50.0 - ((days_ago - 30) / 60) * 40, 2)
        else:
            return 10.0

    return date_series.apply(_score_one)


# ======================================================================
# GitHub 趋势评分
# ======================================================================

def score_github_repos(df: pd.DataFrame) -> pd.DataFrame:
    """
    为 GitHub 仓库 DataFrame 计算趋势评分。

    输入字段：repo_name, owner, description, stars, forks, open_issues,
              language, created_at, updated_at, repo_url, source
    输出字段：原始字段 + trend_score + ranking

    评分公式：
        trend_score = stars_score * 0.4
                    + forks_score * 0.2
                    + issues_score * 0.1
                    + freshness_score * 0.3

    Args:
        df: GitHub 仓库 DataFrame

    Returns:
        带 trend_score 和 ranking 的 DataFrame；空输入返回空 DataFrame
    """
    if df.empty:
        return df.copy()

    result = df.copy()

    # 确保数值字段存在
    for col in ["stars", "forks", "open_issues"]:
        if col not in result.columns:
            result[col] = 0

    # 确保日期字段存在
    if "updated_at" not in result.columns:
        result["updated_at"] = ""

    # 归一化各维度
    stars_score = normalize_series(result["stars"])
    forks_score = normalize_series(result["forks"])
    issues_score = normalize_series(result["open_issues"])
    freshness_score = calculate_freshness_score(result["updated_at"])

    # 加权求和
    result["trend_score"] = (
        stars_score * 0.4
        + forks_score * 0.2
        + issues_score * 0.1
        + freshness_score * 0.3
    ).round(2)

    # 确保范围 0-100
    result["trend_score"] = result["trend_score"].clip(0, 100)

    # 按 trend_score 降序排列并添加排名
    result = result.sort_values("trend_score", ascending=False).reset_index(drop=True)
    result["ranking"] = range(1, len(result) + 1)

    logger.info(f"GitHub 趋势评分完成：{len(result)} 条数据")
    return result


# ======================================================================
# Hacker News 趋势评分
# ======================================================================

def score_hn_items(df: pd.DataFrame) -> pd.DataFrame:
    """
    为 Hacker News 帖子 DataFrame 计算趋势评分。

    输入字段：title, author, points, comments_count, created_at, url, source
    输出字段：原始字段 + trend_score + ranking

    评分公式：
        trend_score = points_score * 0.4
                    + comments_score * 0.3
                    + freshness_score * 0.3

    Args:
        df: HN 帖子 DataFrame

    Returns:
        带 trend_score 和 ranking 的 DataFrame；空输入返回空 DataFrame
    """
    if df.empty:
        return df.copy()

    result = df.copy()

    # 确保数值字段存在
    for col in ["points", "comments_count"]:
        if col not in result.columns:
            result[col] = 0

    # 确保日期字段存在
    if "created_at" not in result.columns:
        result["created_at"] = ""

    # 归一化各维度
    points_score = normalize_series(result["points"])
    comments_score = normalize_series(result["comments_count"])
    freshness_score = calculate_freshness_score(result["created_at"])

    # 加权求和
    result["trend_score"] = (
        points_score * 0.4
        + comments_score * 0.3
        + freshness_score * 0.3
    ).round(2)

    # 确保范围 0-100
    result["trend_score"] = result["trend_score"].clip(0, 100)

    # 按 trend_score 降序排列并添加排名
    result = result.sort_values("trend_score", ascending=False).reset_index(drop=True)
    result["ranking"] = range(1, len(result) + 1)

    logger.info(f"HN 趋势评分完成：{len(result)} 条数据")
    return result


# ======================================================================
# 旧版 ScoringService（保留供 tests 兼容）
# ======================================================================

class ScoringService:
    """
    计算每条数据的趋势评分（旧版接口，保留供兼容性测试）。
    评分维度：原始热度、时间衰减、来源权重。
    """

    # 来源权重配置
    SOURCE_WEIGHTS = {
        "github": 1.0,
        "hackernews": 1.2,
    }

    def calculate_score(self, item: Dict[str, Any], reference_date: datetime = None) -> float:
        """
        为单条数据计算综合趋势评分。

        Args:
            item: 数据条目，需包含 score（原始热度）和 date（YYYY-MM-DD）字段
            reference_date: 参考日期，默认为当前时间

        Returns:
            0~100 的浮点数评分
        """
        if reference_date is None:
            reference_date = datetime.now()

        raw_score = item.get("score", 0)
        source = item.get("source", "github")
        date_str = item.get("date", "")

        try:
            item_date = datetime.strptime(date_str, "%Y-%m-%d")
            days_ago = max(0, (reference_date - item_date).days)
        except (ValueError, TypeError):
            days_ago = 30

        time_decay = 1.0 / (1.0 + days_ago * 0.05)
        source_weight = self.SOURCE_WEIGHTS.get(source, 1.0)

        import math
        log_score = math.log1p(raw_score)

        final_score = log_score * time_decay * source_weight * 10
        final_score = min(100.0, max(0.0, final_score))

        return round(final_score, 2)

    def score_all(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        为一批数据批量计算评分。

        Args:
            items: 数据条目列表

        Returns:
            附加了 trend_score 字段的条目列表
        """
        reference_date = datetime.now()
        for item in items:
            item["trend_score"] = self.calculate_score(item, reference_date)
        return items
