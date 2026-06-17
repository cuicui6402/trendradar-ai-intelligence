"""
database 包
负责 SQLite 连接管理与数据表定义。
"""

from database.db import get_engine, get_session, init_db
from database.models import (
    Base, TrendItem, AnalysisRecord,
    SearchHistory, GitHubResult, HNResult,
)
from database.repository import (
    save_search, save_github_results, save_hn_results,
    get_recent_searches,
)

__all__ = [
    "get_engine", "get_session", "init_db",
    "Base", "TrendItem", "AnalysisRecord",
    "SearchHistory", "GitHubResult", "HNResult",
    "save_search", "save_github_results", "save_hn_results",
    "get_recent_searches",
]
