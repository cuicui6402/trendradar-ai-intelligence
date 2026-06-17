"""
collectors/github_collector.py
GitHub 数据采集器 — 多级 fallback 查询策略。

查询优先级：
  Level 1 (strict)  ：{keyword} pushed:>{date}
  Level 2 (fallback)：{keyword} in:name,description,topics
  Level 3 (broad)   ：{keyword}

API 文档：https://docs.github.com/en/rest/search/search#search-repositories
匿名请求限制：10 次/分钟；携带 Token 限制：30 次/分钟。
"""

import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

import pandas as pd
import requests

from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class GitHubCollector(BaseCollector):
    """
    GitHub 仓库采集器。
    调用 GitHub Search Repositories API，按 star 数排序。
    当严格查询（限定近 N 天推送）无结果时，自动降级到更宽松的查询条件。
    支持可选 GITHUB_TOKEN，未配置时以匿名方式运行（速率较低）。
    """

    API_URL = "https://api.github.com/search/repositories"

    # 请求状态常量
    STATUS_OK = "ok"
    STATUS_EMPTY = "empty"
    STATUS_RATE_LIMITED = "api_rate_limited"
    STATUS_NETWORK_ERROR = "network_error"
    STATUS_API_ERROR = "api_error"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
        })
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            self.session.headers.update({"Authorization": f"token {token}"})
            logger.info("GitHubCollector：已加载 GITHUB_TOKEN（30 次/分钟）")
        else:
            logger.info("GitHubCollector：未配置 GITHUB_TOKEN，使用匿名接口（10 次/分钟）")

        # 每次 collect 后填充，供上层读取
        self.last_result_meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def collect(self, keyword: str, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """
        采集 GitHub 仓库数据，返回字典列表。

        Args:
            keyword: 搜索关键词
            days: 搜索最近 N 天内更新过的仓库（用于严格查询，宽松查询忽略此条件）
            limit: 最多返回条数（上限 100）

        Returns:
            标准化数据条目列表；失败时返回空列表。
        """
        return self._fetch_with_fallback(keyword, days, limit)

    def collect_df(self, keyword: str, days: int = 30, limit: int = 20) -> pd.DataFrame:
        """
        采集 GitHub 仓库数据，返回 Pandas DataFrame。
        调用后通过 self.last_result_meta 获取查询元信息。

        Args:
            keyword: 搜索关键词
            days: 搜索最近 N 天内更新过的仓库
            limit: 最多返回条数

        Returns:
            包含仓库信息的 DataFrame；失败时返回空 DataFrame。
        """
        items = self._fetch_with_fallback(keyword, days, limit)
        if not items:
            return pd.DataFrame(columns=self._columns())
        return pd.DataFrame(items)

    # ------------------------------------------------------------------
    # 多级 fallback 查询
    # ------------------------------------------------------------------

    def _fetch_with_fallback(
        self, keyword: str, days: int, limit: int
    ) -> List[Dict[str, Any]]:
        """
        按优先级依次尝试三级查询，命中即返回。

        Level 1 - strict   ：{keyword} pushed:>{date}
        Level 2 - fallback ：{keyword} in:name,description,topics
        Level 3 - broad    ：{keyword}

        Returns:
            标准化数据条目列表。last_result_meta 记录最终使用的查询级别和原因。
        """
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 定义查询级别
        queries = [
            {
                "level": "strict",
                "q": f"{keyword} pushed:>{since_date}",
                "label": f"严格查询（近 {days} 天活跃）",
                "empty_reason": "strict_search_empty",
            },
            {
                "level": "fallback",
                "q": f"{keyword} in:name,description,topics",
                "label": "名称/描述/标签匹配",
                "empty_reason": "fallback_search_empty",
            },
            {
                "level": "broad",
                "q": keyword,
                "label": "全量关键词搜索",
                "empty_reason": "broad_search_empty",
            },
        ]

        # 用于记录最终状态
        last_error_reason = None

        for query_info in queries:
            level = query_info["level"]
            query_str = query_info["q"]
            empty_reason = query_info["empty_reason"]

            logger.info(f"GitHubCollector [{level}]：尝试查询 q={query_str}")

            items, status, message = self._try_query(query_str, limit)

            if status == self.STATUS_OK and items:
                # 命中结果，记录元信息并返回
                self.last_result_meta = {
                    "query_level": level,
                    "query_string": query_str,
                    "total_count": len(items),
                    "fallback_used": level != "strict",
                    "days": days,
                }
                logger.info(
                    f"GitHubCollector [{level}]：成功采集 {len(items)} 条"
                )
                return items

            # 未命中，记录原因并继续
            if status == self.STATUS_RATE_LIMITED:
                last_error_reason = self.STATUS_RATE_LIMITED
                logger.warning(f"GitHubCollector [{level}]：触发 API rate limit")
                # rate limit 不需要继续尝试下一级，直接返回空
                self.last_result_meta = {
                    "query_level": level,
                    "query_string": query_str,
                    "total_count": 0,
                    "error_reason": self.STATUS_RATE_LIMITED,
                    "error_message": message,
                    "fallback_used": level != "strict",
                    "days": days,
                }
                return []

            if status == self.STATUS_NETWORK_ERROR:
                last_error_reason = self.STATUS_NETWORK_ERROR
                logger.warning(f"GitHubCollector [{level}]：网络错误 - {message}")
                # 网络问题同样不需要继续尝试
                self.last_result_meta = {
                    "query_level": level,
                    "query_string": query_str,
                    "total_count": 0,
                    "error_reason": self.STATUS_NETWORK_ERROR,
                    "error_message": message,
                    "fallback_used": level != "strict",
                    "days": days,
                }
                return []

            if status == self.STATUS_API_ERROR:
                last_error_reason = self.STATUS_API_ERROR
                logger.warning(f"GitHubCollector [{level}]：API 错误 - {message}")
                # API 错误继续尝试下一级
                continue

            # status == EMPTY
            last_error_reason = empty_reason
            logger.info(f"GitHubCollector [{level}]：{empty_reason}，尝试下一级")

        # 所有级别都未命中
        self.last_result_meta = {
            "query_level": "none",
            "query_string": "",
            "total_count": 0,
            "error_reason": last_error_reason or "all_levels_empty",
            "fallback_used": True,
            "days": days,
        }
        logger.info(f"GitHubCollector：所有查询级别均未找到结果（keyword={keyword}）")
        return []

    # ------------------------------------------------------------------
    # 单次请求
    # ------------------------------------------------------------------

    def _try_query(
        self, query: str, limit: int
    ) -> Tuple[List[Dict[str, Any]], str, str]:
        """
        执行单次 GitHub API 查询。

        Returns:
            (items, status, message)
            - items: 解析后的标准化条目列表
            - status: 状态码（STATUS_OK / STATUS_EMPTY / STATUS_RATE_LIMITED / STATUS_NETWORK_ERROR / STATUS_API_ERROR）
            - message: 人可读的描述
        """
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(limit, 100),
        }

        try:
            resp = self.session.get(
                self.API_URL,
                params=params,
                timeout=self.REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            return [], self.STATUS_NETWORK_ERROR, "请求超时"
        except requests.exceptions.ConnectionError as e:
            return [], self.STATUS_NETWORK_ERROR, f"连接失败：{e}"
        except requests.exceptions.RequestException as e:
            return [], self.STATUS_NETWORK_ERROR, f"请求异常：{e}"

        # HTTP 状态码判断
        if resp.status_code == 403:
            # 通常是 rate limit
            return [], self.STATUS_RATE_LIMITED, f"HTTP 403（可能触发 rate limit）"
        if resp.status_code == 422:
            return [], self.STATUS_API_ERROR, f"HTTP 422 查询参数无效"
        if resp.status_code != 200:
            return [], self.STATUS_API_ERROR, f"HTTP {resp.status_code}"

        # 解析 JSON
        try:
            data = resp.json()
        except ValueError:
            return [], self.STATUS_API_ERROR, "响应 JSON 解析失败"

        # 检查 API 级别错误信息
        if "message" in data and "items" not in data:
            msg = data.get("message", "")
            if "rate limit" in msg.lower():
                return [], self.STATUS_RATE_LIMITED, msg
            return [], self.STATUS_API_ERROR, msg

        raw_items = data.get("items", [])
        if not raw_items:
            return [], self.STATUS_EMPTY, "无匹配结果"

        # 解析每条仓库数据
        results = []
        for repo in raw_items:
            try:
                results.append(self._parse_repo(repo))
            except Exception as e:
                logger.warning(f"解析仓库数据时出错，跳过该条目：{e}")
                continue

        if not results:
            return [], self.STATUS_EMPTY, "所有条目解析失败"

        return results, self.STATUS_OK, f"成功获取 {len(results)} 条"

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _columns(self) -> list:
        """DataFrame 标准列名。"""
        return [
            "repo_name", "owner", "description", "stars", "forks",
            "open_issues", "language", "created_at", "updated_at",
            "repo_url", "source",
        ]

    @staticmethod
    def _parse_repo(repo: dict) -> Dict[str, Any]:
        """
        从 GitHub API 单条仓库 JSON 中提取标准化字段。
        字段缺失时使用安全默认值。
        """
        return {
            "repo_name": repo.get("name", "unknown"),
            "owner": repo.get("owner", {}).get("login", "unknown"),
            "description": (repo.get("description") or "")[:200],
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "language": repo.get("language") or "N/A",
            "created_at": repo.get("created_at", "")[:10],
            "updated_at": repo.get("updated_at", "")[:10],
            "repo_url": repo.get("html_url", ""),
            "source": "github",
        }
