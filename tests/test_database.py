"""
tests/test_database.py
数据库功能测试。
使用临时数据库文件，测试完成后自动清理。
"""

import sys
import os
import tempfile
from datetime import datetime

import pandas as pd

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用临时数据库文件
_test_db_path = None


def _get_test_db():
    """获取临时数据库路径，并重置数据库模块状态。"""
    global _test_db_path
    if _test_db_path is None:
        fd, _test_db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
    # 重置 db 模块状态，确保使用新的数据库路径
    import database.db as db_module
    db_module._initialized = False
    db_module._current_db_path = _test_db_path
    return _test_db_path


def _cleanup():
    """清理临时数据库文件。"""
    global _test_db_path
    if _test_db_path and os.path.exists(_test_db_path):
        # 重置模块状态
        import database.db as db_module
        db_module._initialized = False
        db_module._current_db_path = db_module.DEFAULT_DB_PATH
        try:
            os.remove(_test_db_path)
        except PermissionError:
            pass  # Windows 文件锁，忽略
        _test_db_path = None


# ======================================================================
# 测试用例
# ======================================================================

def test_init_db():
    """测试数据库初始化。"""
    from database.db import init_db, get_engine
    from database.models import Base

    db_path = _get_test_db()
    init_db(db_path)

    # 验证表是否创建
    engine = get_engine(db_path)
    tables = engine.table_names() if hasattr(engine, 'table_names') else []

    # SQLAlchemy 2.0 方式
    from sqlalchemy import inspect
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    assert "search_history" in table_names, f"search_history 表未创建，现有表：{table_names}"
    assert "github_results" in table_names, f"github_results 表未创建"
    assert "hn_results" in table_names, f"hn_results 表未创建"
    assert "reports" in table_names, f"reports 表未创建"

    print("  [PASS] 数据库初始化验证通过")


def test_save_search():
    """测试保存搜索历史。"""
    from database.db import init_db
    from database.repository import save_search

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("FastAPI", 30, 15, 8)
    assert search_id is not None, "save_search 应返回有效的 search_id"
    assert isinstance(search_id, int), f"search_id 应为 int，实际为 {type(search_id)}"
    print(f"  保存搜索历史：id={search_id}")
    print("  [PASS] save_search 验证通过")

    return search_id


def test_save_github_results():
    """测试保存 GitHub 评分结果。"""
    from database.db import init_db
    from database.repository import save_search, save_github_results

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("LangGraph", 30, 3, 0)

    # 构造测试 DataFrame
    scored_df = pd.DataFrame({
        "ranking": [1, 2, 3],
        "repo_name": ["repo-a", "repo-b", "repo-c"],
        "owner": ["user1", "user2", "user3"],
        "description": ["desc1", "desc2", "desc3"],
        "stars": [1000, 500, 100],
        "forks": [200, 100, 20],
        "open_issues": [50, 30, 5],
        "language": ["Python", "Python", "Python"],
        "created_at": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "updated_at": ["2026-06-15", "2026-06-10", "2026-06-01"],
        "repo_url": ["url1", "url2", "url3"],
        "source": ["github", "github", "github"],
        "trend_score": [95.5, 65.3, 35.0],
    })

    result = save_github_results(search_id, scored_df)
    assert result is True, "save_github_results 应返回 True"
    print(f"  保存 GitHub 结果：search_id={search_id}, count=3")
    print("  [PASS] save_github_results 验证通过")


def test_save_hn_results():
    """测试保存 HN 评分结果。"""
    from database.db import init_db
    from database.repository import save_search, save_hn_results

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("AI Agent", 30, 0, 3)

    scored_df = pd.DataFrame({
        "ranking": [1, 2, 3],
        "title": ["Title A", "Title B", "Title C"],
        "author": ["user1", "user2", "user3"],
        "points": [500, 200, 50],
        "comments_count": [100, 50, 10],
        "created_at": ["2026-06-15", "2026-06-10", "2026-06-01"],
        "url": ["url1", "url2", "url3"],
        "source": ["hackernews", "hackernews", "hackernews"],
        "trend_score": [92.0, 55.5, 28.0],
    })

    result = save_hn_results(search_id, scored_df)
    assert result is True, "save_hn_results 应返回 True"
    print(f"  保存 HN 结果：search_id={search_id}, count=3")
    print("  [PASS] save_hn_results 验证通过")


def test_get_recent_searches():
    """测试查询最近搜索历史。"""
    from database.db import init_db
    from database.repository import save_search, get_recent_searches

    db_path = _get_test_db()
    init_db(db_path)

    # 插入多条搜索记录
    save_search("FastAPI", 30, 10, 5)
    save_search("LangGraph", 7, 8, 3)
    save_search("RAG", 90, 20, 12)

    history = get_recent_searches(limit=10)
    assert len(history) >= 3, f"应至少有 3 条记录，实际 {len(history)} 条"

    # 验证按时间降序
    assert history[0]["keyword"] == "RAG", "最新记录应在最前面"
    assert history[1]["keyword"] == "LangGraph", "第二条应为 LangGraph"
    assert history[2]["keyword"] == "FastAPI", "第三条应为 FastAPI"

    # 验证字段完整
    first = history[0]
    assert "id" in first, "应包含 id 字段"
    assert "keyword" in first, "应包含 keyword 字段"
    assert "days" in first, "应包含 days 字段"
    assert "github_count" in first, "应包含 github_count 字段"
    assert "hn_count" in first, "应包含 hn_count 字段"
    assert "created_at" in first, "应包含 created_at 字段"

    print(f"  查询到 {len(history)} 条历史记录")
    for h in history[:3]:
        print(f"    - {h['keyword']} ({h['days']}天) GH:{h['github_count']} HN:{h['hn_count']}")
    print("  [PASS] get_recent_searches 验证通过")


def test_save_empty_results():
    """测试保存空结果（不应报错）。"""
    from database.db import init_db
    from database.repository import save_search, save_github_results, save_hn_results

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("empty-test", 30, 0, 0)
    assert search_id is not None

    # 空 DataFrame 不应报错
    empty_df = pd.DataFrame()
    assert save_github_results(search_id, empty_df) is True
    assert save_hn_results(search_id, empty_df) is True

    # None 也不应报错
    assert save_github_results(search_id, None) is True
    assert save_hn_results(search_id, None) is True

    print("  [PASS] 空结果保存验证通过")


# ======================================================================
# Phase 8.5 历史记录读取测试
# ======================================================================

def _make_scored_data():
    """构造测试用的 GitHub 和 HN 评分 DataFrame。"""
    gh_df = pd.DataFrame({
        "ranking": [1, 2, 3],
        "repo_name": ["repo-a", "repo-b", "repo-c"],
        "owner": ["user1", "user2", "user3"],
        "description": ["desc1", "desc2", "desc3"],
        "stars": [1000, 500, 100],
        "forks": [200, 100, 20],
        "open_issues": [50, 30, 5],
        "language": ["Python", "Python", "TypeScript"],
        "created_at": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "updated_at": ["2026-06-15", "2026-06-10", "2026-06-01"],
        "repo_url": ["url1", "url2", "url3"],
        "source": ["github", "github", "github"],
        "trend_score": [95.5, 65.3, 35.0],
    })
    hn_df = pd.DataFrame({
        "ranking": [1, 2],
        "title": ["HN Title A", "HN Title B"],
        "author": ["author1", "author2"],
        "points": [300, 120],
        "comments_count": [80, 30],
        "created_at": ["2026-06-14", "2026-06-10"],
        "url": ["hn_url1", "hn_url2"],
        "source": ["hackernews", "hackernews"],
        "trend_score": [88.0, 52.0],
    })
    return gh_df, hn_df


def test_get_search_by_id():
    """测试通过 search_id 读取搜索历史。"""
    from database.db import init_db
    from database.repository import save_search, get_search_by_id

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("TestKw", 14, 10, 5)
    assert search_id is not None

    record = get_search_by_id(search_id)
    assert record is not None, "应能读取刚保存的搜索记录"
    assert record["keyword"] == "TestKw"
    assert record["days"] == 14
    assert record["github_count"] == 10
    assert record["hn_count"] == 5
    assert record["id"] == search_id

    print("  [PASS] get_search_by_id 验证通过")


def test_get_github_results_by_search():
    """测试通过 search_id 读取 GitHub 结果。"""
    from database.db import init_db
    from database.repository import (
        save_search, save_github_results, get_github_results_by_search,
    )

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("GH-Read-Test", 30, 3, 0)
    gh_df, _ = _make_scored_data()
    save_github_results(search_id, gh_df)

    result = get_github_results_by_search(search_id)
    assert not result.empty, "应能读取刚保存的 GitHub 结果"
    assert len(result) == 3, f"应有 3 条记录，实际 {len(result)} 条"
    assert "trend_score" in result.columns
    assert "repo_name" in result.columns
    # 验证按 ranking 排序
    assert list(result["ranking"]) == [1, 2, 3]

    print("  [PASS] get_github_results_by_search 验证通过")


def test_get_hn_results_by_search():
    """测试通过 search_id 读取 Hacker News 结果。"""
    from database.db import init_db
    from database.repository import (
        save_search, save_hn_results, get_hn_results_by_search,
    )

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("HN-Read-Test", 30, 0, 2)
    _, hn_df = _make_scored_data()
    save_hn_results(search_id, hn_df)

    result = get_hn_results_by_search(search_id)
    assert not result.empty, "应能读取刚保存的 HN 结果"
    assert len(result) == 2, f"应有 2 条记录，实际 {len(result)} 条"
    assert "trend_score" in result.columns
    assert "title" in result.columns

    print("  [PASS] get_hn_results_by_search 验证通过")


def test_get_latest_report_by_search():
    """测试读取最新报告。"""
    from database.db import init_db
    from database.repository import (
        save_search, save_report, get_latest_report_by_search,
    )

    db_path = _get_test_db()
    init_db(db_path)

    search_id = save_search("Report-Read-Test", 30, 5, 3)

    # 保存前没有报告
    report = get_latest_report_by_search(search_id)
    assert report is None, "保存前应无报告"

    # 保存报告
    save_report(search_id, "测试报告", "# 报告正文", "data/reports/test.md")

    report = get_latest_report_by_search(search_id)
    assert report is not None, "保存后应能读取报告"
    assert report["report_title"] == "测试报告"
    assert report["report_content"] == "# 报告正文"
    assert report["markdown_path"] == "data/reports/test.md"

    print("  [PASS] get_latest_report_by_search 验证通过")


def test_nonexistent_search_id():
    """测试不存在的 search_id 不报错。"""
    from database.db import init_db
    from database.repository import (
        get_search_by_id,
        get_github_results_by_search,
        get_hn_results_by_search,
        get_latest_report_by_search,
    )

    db_path = _get_test_db()
    init_db(db_path)

    fake_id = 999999

    assert get_search_by_id(fake_id) is None, "不存在的 ID 应返回 None"
    assert get_github_results_by_search(fake_id).empty, "不存在的 ID 应返回空 DataFrame"
    assert get_hn_results_by_search(fake_id).empty, "不存在的 ID 应返回空 DataFrame"
    assert get_latest_report_by_search(fake_id) is None, "不存在的 ID 应返回 None"

    print("  [PASS] 不存在的 search_id 验证通过")


# ======================================================================
# 测试运行器
# ======================================================================

def run_database_test():
    """运行所有数据库测试。"""
    print("运行数据库测试...")
    print()
    try:
        test_init_db()
        test_save_search()
        test_save_github_results()
        test_save_hn_results()
        test_get_recent_searches()
        test_save_empty_results()
        # Phase 8.5 历史读取测试
        test_get_search_by_id()
        test_get_github_results_by_search()
        test_get_hn_results_by_search()
        test_get_latest_report_by_search()
        test_nonexistent_search_id()
        print()
        print("所有数据库测试通过！")
    finally:
        _cleanup()


if __name__ == "__main__":
    run_database_test()
