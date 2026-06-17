"""
tests/test_scoring.py
评分服务的单元测试。
覆盖旧版 ScoringService 和新版 DataFrame 评分函数。
"""

import sys
import os
from datetime import datetime, timedelta

import pandas as pd

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.scoring_service import (
    ScoringService,
    normalize_series,
    calculate_freshness_score,
    score_github_repos,
    score_hn_items,
)


# ======================================================================
# 旧版 ScoringService 测试（保留兼容）
# ======================================================================

def test_score_calculation():
    """测试旧版评分计算基本逻辑。"""
    service = ScoringService()
    today = datetime.now()

    # 测试：今天的高 star 项目应得到较高分
    item = {
        "title": "test-repo",
        "url": "https://github.com/test",
        "source": "github",
        "date": today.strftime("%Y-%m-%d"),
        "score": 500,
        "description": "test",
    }
    score = service.calculate_score(item, today)
    assert 0 <= score <= 100, f"评分应介于 0~100，实际为 {score}"
    print(f"  今天 500 star 的 GitHub 项目评分：{score}")

    # 测试：30 天前的项目应得到较低分
    old_item = item.copy()
    old_item["date"] = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    old_score = service.calculate_score(old_item, today)
    assert old_score < score, f"30天前的评分({old_score})应低于今天的评分({score})"
    print(f"  30天前 500 star 的 GitHub 项目评分：{old_score}")

    # 测试：HN 来源应有额外权重
    hn_item = item.copy()
    hn_item["source"] = "hackernews"
    hn_score = service.calculate_score(hn_item, today)
    assert hn_score >= score, f"HN 评分({hn_score})应不低于 GitHub 评分({score})"
    print(f"  今天 500 分的 HN 帖子评分：{hn_score}")

    print("  [PASS] 旧版评分计算逻辑验证通过")


def test_score_all():
    """测试旧版批量评分。"""
    service = ScoringService()
    today = datetime.now()
    items = [
        {
            "title": f"item-{i}",
            "url": f"https://example.com/{i}",
            "source": "github" if i % 2 == 0 else "hackernews",
            "date": (today - timedelta(days=i)).strftime("%Y-%m-%d"),
            "score": 100 + i * 50,
            "description": f"Test item {i}",
        }
        for i in range(5)
    ]

    scored = service.score_all(items)
    assert all("trend_score" in item for item in scored), "所有条目应包含 trend_score 字段"
    print(f"  批量评分结果：{[item['trend_score'] for item in scored]}")
    print("  [PASS] 旧版批量评分逻辑验证通过")


# ======================================================================
# 新版 DataFrame 评分测试
# ======================================================================

def test_normalize_series():
    """测试数值归一化。"""
    # 正常情况
    s = pd.Series([0, 50, 100])
    result = normalize_series(s)
    assert result.min() == 0.0, f"最小值应为 0，实际为 {result.min()}"
    assert result.max() == 100.0, f"最大值应为 100，实际为 {result.max()}"

    # 全部相同值
    s_same = pd.Series([5, 5, 5])
    result_same = normalize_series(s_same)
    assert all(result_same == 50.0), "全部相同时应返回 50"

    # 包含空值
    s_null = pd.Series([10, None, 30])
    result_null = normalize_series(s_null)
    assert 0 <= result_null.min() <= 100, "空值应被正确处理"

    # 包含非数值
    s_mixed = pd.Series([10, "abc", 30])
    result_mixed = normalize_series(s_mixed)
    assert len(result_mixed) == 3, "非数值应被转换"

    print("  [PASS] normalize_series 验证通过")


def test_calculate_freshness_score():
    """测试时间新鲜度评分。"""
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    old = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")

    dates = pd.Series([today, week_ago, month_ago, old])
    scores = calculate_freshness_score(dates)

    # 今天应该最高分
    assert scores.iloc[0] == 100.0, f"今天应得 100 分，实际为 {scores.iloc[0]}"
    # 越旧分数越低
    assert scores.iloc[0] > scores.iloc[1] > scores.iloc[2] > scores.iloc[3], "时间越旧分数应越低"
    # 超过 90 天应得低分
    assert scores.iloc[3] == 10.0, f"超过90天应得10分，实际为 {scores.iloc[3]}"

    # 异常日期应得低分
    bad_dates = pd.Series(["invalid", "", None])
    bad_scores = calculate_freshness_score(bad_dates)
    assert all(bad_scores == 10.0), "异常日期应得 10 分"

    print("  [PASS] calculate_freshness_score 验证通过")


def test_score_github_repos_empty():
    """测试空 DataFrame。"""
    empty_df = pd.DataFrame()
    result = score_github_repos(empty_df)
    assert result.empty, "空输入应返回空 DataFrame"
    print("  [PASS] score_github_repos 空 DataFrame 验证通过")


def test_score_github_repos_normal():
    """测试正常 GitHub DataFrame 评分。"""
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    df = pd.DataFrame({
        "repo_name": ["repo-a", "repo-b", "repo-c"],
        "owner": ["user1", "user2", "user3"],
        "description": ["desc1", "desc2", "desc3"],
        "stars": [1000, 500, 100],
        "forks": [200, 100, 20],
        "open_issues": [50, 30, 5],
        "language": ["Python", "Python", "Python"],
        "created_at": [today, today, today],
        "updated_at": [today, week_ago, week_ago],
        "repo_url": ["url1", "url2", "url3"],
        "source": ["github", "github", "github"],
    })

    result = score_github_repos(df)

    # 检查输出字段
    assert "trend_score" in result.columns, "应包含 trend_score 字段"
    assert "ranking" in result.columns, "应包含 ranking 字段"

    # 检查评分范围
    assert all(result["trend_score"] >= 0), "评分不应小于 0"
    assert all(result["trend_score"] <= 100), "评分不应大于 100"

    # 检查排名顺序
    assert list(result["ranking"]) == list(range(1, len(result) + 1)), "排名应从 1 开始连续递增"

    # 检查按 trend_score 降序排列
    scores = result["trend_score"].tolist()
    assert scores == sorted(scores, reverse=True), "结果应按 trend_score 降序排列"

    print(f"  GitHub 评分结果：{result[['repo_name', 'trend_score', 'ranking']].to_dict('records')}")
    print("  [PASS] score_github_repos 正常 DataFrame 验证通过")


def test_score_github_repos_missing_fields():
    """测试缺失字段。"""
    df = pd.DataFrame({
        "repo_name": ["repo-a"],
        "owner": ["user1"],
        "source": ["github"],
        # 缺失 stars, forks, open_issues, updated_at
    })

    result = score_github_repos(df)
    assert not result.empty, "缺失字段时不应返回空"
    assert "trend_score" in result.columns, "应包含 trend_score 字段"
    assert 0 <= result["trend_score"].iloc[0] <= 100, "评分应在 0-100 范围内"

    print("  [PASS] score_github_repos 缺失字段验证通过")


def test_score_hn_items_empty():
    """测试空 DataFrame。"""
    empty_df = pd.DataFrame()
    result = score_hn_items(empty_df)
    assert result.empty, "空输入应返回空 DataFrame"
    print("  [PASS] score_hn_items 空 DataFrame 验证通过")


def test_score_hn_items_normal():
    """测试正常 HN DataFrame 评分。"""
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    df = pd.DataFrame({
        "title": ["Title A", "Title B", "Title C"],
        "author": ["user1", "user2", "user3"],
        "points": [500, 200, 50],
        "comments_count": [100, 50, 10],
        "created_at": [today, week_ago, week_ago],
        "url": ["url1", "url2", "url3"],
        "source": ["hackernews", "hackernews", "hackernews"],
    })

    result = score_hn_items(df)

    # 检查输出字段
    assert "trend_score" in result.columns, "应包含 trend_score 字段"
    assert "ranking" in result.columns, "应包含 ranking 字段"

    # 检查评分范围
    assert all(result["trend_score"] >= 0), "评分不应小于 0"
    assert all(result["trend_score"] <= 100), "评分不应大于 100"

    # 检查排名顺序
    assert list(result["ranking"]) == list(range(1, len(result) + 1)), "排名应从 1 开始连续递增"

    # 检查按 trend_score 降序排列
    scores = result["trend_score"].tolist()
    assert scores == sorted(scores, reverse=True), "结果应按 trend_score 降序排列"

    print(f"  HN 评分结果：{result[['title', 'trend_score', 'ranking']].to_dict('records')}")
    print("  [PASS] score_hn_items 正常 DataFrame 验证通过")


def test_score_hn_items_abnormal_dates():
    """测试时间字段异常。"""
    df = pd.DataFrame({
        "title": ["Title A", "Title B"],
        "author": ["user1", "user2"],
        "points": [100, 50],
        "comments_count": [20, 10],
        "created_at": ["invalid-date", ""],  # 异常日期
        "url": ["url1", "url2"],
        "source": ["hackernews", "hackernews"],
    })

    result = score_hn_items(df)
    assert not result.empty, "异常日期时不应返回空"
    assert all(result["trend_score"] >= 0), "评分不应小于 0"
    assert all(result["trend_score"] <= 100), "评分不应大于 100"

    print("  [PASS] score_hn_items 异常日期验证通过")


# ======================================================================
# 测试运行器
# ======================================================================

def run_basic_test():
    """运行所有测试（供 main.py test 调用）。"""
    print("运行 ScoringService 测试...")
    print()
    print("--- 旧版接口测试 ---")
    test_score_calculation()
    test_score_all()
    print()
    print("--- 新版 DataFrame 评分测试 ---")
    test_normalize_series()
    test_calculate_freshness_score()
    test_score_github_repos_empty()
    test_score_github_repos_normal()
    test_score_github_repos_missing_fields()
    test_score_hn_items_empty()
    test_score_hn_items_normal()
    test_score_hn_items_abnormal_dates()
    print()
    print("所有测试通过！")


if __name__ == "__main__":
    run_basic_test()
