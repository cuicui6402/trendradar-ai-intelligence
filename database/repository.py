"""
database/repository.py
搜索历史的存取函数。
app.py 只调用这里的函数，不直接写 SQL 或 ORM 操作。
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import pandas as pd

from database.db import get_session
from database.models import SearchHistory, GitHubResult, HNResult, Report

logger = logging.getLogger(__name__)


# ======================================================================
# 写入
# ======================================================================

def save_search(
    keyword: str,
    days: int,
    github_count: int = 0,
    hn_count: int = 0,
) -> Optional[int]:
    """
    保存一条搜索历史记录。

    Args:
        keyword: 搜索关键词
        days: 时间范围（天）
        github_count: GitHub 结果数量
        hn_count: HN 结果数量

    Returns:
        搜索记录 ID；失败时返回 None
    """
    try:
        session = get_session()
        record = SearchHistory(
            keyword=keyword,
            days=days,
            github_count=github_count,
            hn_count=hn_count,
            created_at=datetime.now(),
        )
        session.add(record)
        session.commit()
        search_id = record.id
        session.close()
        logger.info(f"搜索历史已保存：id={search_id}, keyword={keyword}")
        return search_id
    except Exception as e:
        logger.error(f"保存搜索历史失败：{e}")
        return None


def save_github_results(search_id: int, scored_df: pd.DataFrame) -> bool:
    """
    保存 GitHub 趋势评分结果。

    Args:
        search_id: 关联的搜索记录 ID
        scored_df: 经过 score_github_repos() 评分后的 DataFrame

    Returns:
        是否保存成功
    """
    if scored_df is None or scored_df.empty:
        return True  # 空数据不算失败

    try:
        session = get_session()
        records = []
        for _, row in scored_df.iterrows():
            records.append(GitHubResult(
                search_id=search_id,
                ranking=int(row.get("ranking", 0)),
                repo_name=str(row.get("repo_name", "")),
                owner=str(row.get("owner", "")),
                description=str(row.get("description", ""))[:500],
                stars=int(row.get("stars", 0)),
                forks=int(row.get("forks", 0)),
                open_issues=int(row.get("open_issues", 0)),
                language=str(row.get("language", "")),
                created_at=str(row.get("created_at", "")),
                updated_at=str(row.get("updated_at", "")),
                repo_url=str(row.get("repo_url", "")),
                trend_score=float(row.get("trend_score", 0.0)),
            ))
        session.add_all(records)
        session.commit()
        session.close()
        logger.info(f"GitHub 结果已保存：search_id={search_id}, count={len(records)}")
        return True
    except Exception as e:
        logger.error(f"保存 GitHub 结果失败：{e}")
        return False


def save_hn_results(search_id: int, scored_df: pd.DataFrame) -> bool:
    """
    保存 Hacker News 趋势评分结果。

    Args:
        search_id: 关联的搜索记录 ID
        scored_df: 经过 score_hn_items() 评分后的 DataFrame

    Returns:
        是否保存成功
    """
    if scored_df is None or scored_df.empty:
        return True  # 空数据不算失败

    try:
        session = get_session()
        records = []
        for _, row in scored_df.iterrows():
            records.append(HNResult(
                search_id=search_id,
                ranking=int(row.get("ranking", 0)),
                title=str(row.get("title", ""))[:500],
                author=str(row.get("author", "")),
                points=int(row.get("points", 0)),
                comments_count=int(row.get("comments_count", 0)),
                created_at=str(row.get("created_at", "")),
                url=str(row.get("url", "")),
                trend_score=float(row.get("trend_score", 0.0)),
            ))
        session.add_all(records)
        session.commit()
        session.close()
        logger.info(f"HN 结果已保存：search_id={search_id}, count={len(records)}")
        return True
    except Exception as e:
        logger.error(f"保存 HN 结果失败：{e}")
        return False


# ======================================================================
# 报告
# ======================================================================

def save_report(
    search_id: int,
    report_title: str,
    report_content: str,
    markdown_path: str = "",
) -> Optional[int]:
    """
    保存一份 AI 趋势报告记录。

    Args:
        search_id: 关联的搜索记录 ID
        report_title: 报告标题
        report_content: 报告 Markdown 正文
        markdown_path: Markdown 文件的磁盘保存路径

    Returns:
        报告记录 ID；失败时返回 None
    """
    try:
        session = get_session()
        record = Report(
            search_id=search_id,
            report_title=report_title,
            report_content=report_content,
            markdown_path=markdown_path,
            created_at=datetime.now(),
        )
        session.add(record)
        session.commit()
        report_id = record.id
        session.close()
        logger.info(f"报告已保存：id={report_id}, title={report_title}")
        return report_id
    except Exception as e:
        logger.error(f"保存报告失败：{e}")
        return None


def get_reports_by_search(search_id: int) -> List[Dict[str, Any]]:
    """
    查询某次搜索关联的所有报告。

    Args:
        search_id: 搜索记录 ID

    Returns:
        报告字典列表；失败时返回空列表。
    """
    try:
        session = get_session()
        records = (
            session.query(Report)
            .filter(Report.search_id == search_id)
            .order_by(Report.created_at.desc())
            .all()
        )
        results = []
        for r in records:
            results.append({
                "id": r.id,
                "search_id": r.search_id,
                "report_title": r.report_title,
                "markdown_path": r.markdown_path,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            })
        session.close()
        return results
    except Exception as e:
        logger.error(f"查询报告失败：{e}")
        return []


# ======================================================================
# 查询
# ======================================================================

def get_recent_searches(limit: int = 10) -> List[Dict[str, Any]]:
    """
    查询最近的搜索历史记录。

    Args:
        limit: 返回条数上限

    Returns:
        搜索记录字典列表，按时间降序排列；失败时返回空列表。
    """
    try:
        session = get_session()
        records = (
            session.query(SearchHistory)
            .order_by(SearchHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        results = []
        for r in records:
            results.append({
                "id": r.id,
                "keyword": r.keyword,
                "days": r.days,
                "github_count": r.github_count,
                "hn_count": r.hn_count,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            })
        session.close()
        return results
    except Exception as e:
        logger.error(f"查询搜索历史失败：{e}")
        return []


# ======================================================================
# 历史记录读取（Phase 8.5）
# ======================================================================

def get_search_by_id(search_id: int) -> Optional[Dict[str, Any]]:
    """
    根据 ID 查询单条搜索历史。

    Args:
        search_id: 搜索记录 ID

    Returns:
        搜索记录字典；不存在或失败时返回 None。
    """
    try:
        session = get_session()
        record = session.query(SearchHistory).filter(
            SearchHistory.id == search_id
        ).first()
        if record is None:
            session.close()
            return None
        result = {
            "id": record.id,
            "keyword": record.keyword,
            "days": record.days,
            "github_count": record.github_count,
            "hn_count": record.hn_count,
            "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        }
        session.close()
        return result
    except Exception as e:
        logger.error(f"查询搜索记录失败：{e}")
        return None


def get_github_results_by_search(search_id: int) -> pd.DataFrame:
    """
    查询某次搜索对应的 GitHub 结果。

    Args:
        search_id: 搜索记录 ID

    Returns:
        评分结果 DataFrame（按 ranking 升序）；失败时返回空 DataFrame。
    """
    try:
        session = get_session()
        records = (
            session.query(GitHubResult)
            .filter(GitHubResult.search_id == search_id)
            .order_by(GitHubResult.ranking.asc())
            .all()
        )
        if not records:
            session.close()
            return pd.DataFrame()
        data = []
        for r in records:
            data.append({
                "ranking": r.ranking,
                "repo_name": r.repo_name,
                "owner": r.owner,
                "description": r.description,
                "stars": r.stars,
                "forks": r.forks,
                "open_issues": r.open_issues,
                "language": r.language,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "repo_url": r.repo_url,
                "trend_score": r.trend_score,
            })
        session.close()
        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"查询 GitHub 结果失败：{e}")
        return pd.DataFrame()


def get_hn_results_by_search(search_id: int) -> pd.DataFrame:
    """
    查询某次搜索对应的 Hacker News 结果。

    Args:
        search_id: 搜索记录 ID

    Returns:
        评分结果 DataFrame（按 ranking 升序）；失败时返回空 DataFrame。
    """
    try:
        session = get_session()
        records = (
            session.query(HNResult)
            .filter(HNResult.search_id == search_id)
            .order_by(HNResult.ranking.asc())
            .all()
        )
        if not records:
            session.close()
            return pd.DataFrame()
        data = []
        for r in records:
            data.append({
                "ranking": r.ranking,
                "title": r.title,
                "author": r.author,
                "points": r.points,
                "comments_count": r.comments_count,
                "created_at": r.created_at,
                "url": r.url,
                "trend_score": r.trend_score,
            })
        session.close()
        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"查询 Hacker News 结果失败：{e}")
        return pd.DataFrame()


def get_latest_report_by_search(search_id: int) -> Optional[Dict[str, Any]]:
    """
    查询某次搜索关联的最新报告。

    Args:
        search_id: 搜索记录 ID

    Returns:
        报告字典（含 report_content, markdown_path 等）；无报告或失败时返回 None。
    """
    try:
        session = get_session()
        record = (
            session.query(Report)
            .filter(Report.search_id == search_id)
            .order_by(Report.created_at.desc())
            .first()
        )
        if record is None:
            session.close()
            return None
        result = {
            "id": record.id,
            "search_id": record.search_id,
            "report_title": record.report_title,
            "report_content": record.report_content,
            "markdown_path": record.markdown_path,
            "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        }
        session.close()
        return result
    except Exception as e:
        logger.error(f"查询最新报告失败：{e}")
        return None
