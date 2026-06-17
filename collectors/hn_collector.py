"""
collectors/hn_collector.py
Hacker News 数据采集器 — 接入真实 Algolia HN Search API。

API 文档：https://hn.algolia.com/api
免费接口，无需 Key，无官方速率限制（但建议控制请求频率）。

查询策略（两级 fallback）：
  Level 1 (strict)  ：关键词 + 近 N 天 + tags=story
  Level 2 (broad)   ：关键词 + tags=story（不限时间）
"""

import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta

import pandas as pd
import requests

from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class HNCollector(BaseCollector):
    """
    Hacker News 帖子采集器。
    调用 Algolia HN Search API，按相关性排序，可选时间范围过滤。
    免费接口，无需认证。
    """

    API_URL = "https://hn.algolia.com/api/v1/search"

    # 请求状态常量
    STATUS_OK = "ok"
    STATUS_EMPTY = "empty"
    STATUS_NETWORK_ERROR = "network_error"
    STATUS_API_ERROR = "api_error"

    def __init__(self):
        super().__init__()
        # 每次 collect 后填充，供上层读取
        self.last_result_meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def collect(self, keyword: str, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """
        采集 HN 帖子数据，返回字典列表。

        Args:
            keyword: 搜索关键词
            days: 搜索最近 N 天内的帖子
            limit: 最多返回条数

        Returns:
            标准化数据条目列表；失败时返回空列表。
        """
        return self._fetch_with_fallback(keyword, days, limit)

    def collect_df(self, keyword: str, days: int = 30, limit: int = 20) -> pd.DataFrame:
        """
        采集 HN 帖子数据，返回 Pandas DataFrame。
        调用后通过 self.last_result_meta 获取查询元信息。

        Args:
            keyword: 搜索关键词
            days: 搜索最近 N 天内的帖子
            limit: 最多返回条数

        Returns:
            包含帖子信息的 DataFrame；失败时返回空 DataFrame。
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
        按优先级依次尝试两级查询，命中即返回。

        Level 1 - strict：关键词 + 近 N 天 + tags=story
        Level 2 - broad ：关键词 + tags=story（不限时间）

        Returns:
            标准化数据条目列表。last_result_meta 记录最终使用的查询级别和原因。
        """
        # 计算时间戳（用于 numericFilters）
        since_ts = int((datetime.now() - timedelta(days=days)).timestamp())

        queries = [
            {
                "level": "strict",
                "params": self._build_params(keyword, limit, since_ts),
                "empty_reason": "strict_search_empty",
            },
            {
                "level": "broad",
                "params": self._build_params(keyword, limit, since_ts=None),
                "empty_reason": "broad_search_empty",
            },
        ]

        last_error_reason = None

        for query_info in queries:
            level = query_info["level"]
            params = query_info["params"]
            empty_reason = query_info["empty_reason"]

            logger.info(f"HNCollector [{level}]：尝试搜索 keyword={keyword}")

            items, status, message = self._try_query(params)

            if status == self.STATUS_OK and items:
                self.last_result_meta = {
                    "query_level": level,
                    "total_count": len(items),
                    "fallback_used": level != "strict",
                    "days": days,
                }
                logger.info(f"HNCollector [{level}]：成功采集 {len(items)} 条")
                return items

            if status == self.STATUS_NETWORK_ERROR:
                last_error_reason = self.STATUS_NETWORK_ERROR
                logger.warning(f"HNCollector [{level}]：网络错误 - {message}")
                self.last_result_meta = {
                    "query_level": level,
                    "total_count": 0,
                    "error_reason": self.STATUS_NETWORK_ERROR,
                    "error_message": message,
                    "fallback_used": level != "strict",
                    "days": days,
                }
                return []

            if status == self.STATUS_API_ERROR:
                last_error_reason = self.STATUS_API_ERROR
                logger.warning(f"HNCollector [{level}]：API 错误 - {message}")
                continue

            # status == EMPTY
            last_error_reason = empty_reason
            logger.info(f"HNCollector [{level}]：{empty_reason}，尝试下一级")

        # 所有级别都未命中
        self.last_result_meta = {
            "query_level": "none",
            "total_count": 0,
            "error_reason": last_error_reason or "all_levels_empty",
            "fallback_used": True,
            "days": days,
        }
        logger.info(f"HNCollector：所有查询级别均未找到结果（keyword={keyword}）")
        return []

    # ------------------------------------------------------------------
    # 单次请求
    # ------------------------------------------------------------------

    def _try_query(
        self, params: dict
    ) -> Tuple[List[Dict[str, Any]], str, str]:
        """
        执行单次 HN Algolia API 查询。

        Returns:
            (items, status, message)
        """
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

        if resp.status_code != 200:
            return [], self.STATUS_API_ERROR, f"HTTP {resp.status_code}"

        try:
            data = resp.json()
        except ValueError:
            return [], self.STATUS_API_ERROR, "响应 JSON 解析失败"

        hits = data.get("hits", [])
        if not hits:
            return [], self.STATUS_EMPTY, "无匹配结果"

        # 逐条解析
        results = []
        for hit in hits:
            try:
                results.append(self._parse_hit(hit))
            except Exception as e:
                logger.warning(f"解析 HN 帖子时出错，跳过该条目：{e}")
                continue

        if not results:
            return [], self.STATUS_EMPTY, "所有条目解析失败"

        return results, self.STATUS_OK, f"成功获取 {len(results)} 条"

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_params(keyword: str, limit: int, since_ts: int | None) -> dict:
        """
        构造 Algolia API 查询参数。

        Args:
            keyword: 搜索关键词
            limit: 返回条数上限
            since_ts: Unix 时间戳，为 None 时不限时间

        Returns:
            查询参数字典
        """
        params = {
            "query": keyword,
            "tags": "story",
            "hitsPerPage": min(limit, 100),
        }
        if since_ts is not None:
            params["numericFilters"] = f"created_at_i>{since_ts}"
        return params

    @staticmethod
    def _parse_hit(hit: dict) -> Dict[str, Any]:
        """
        从 Algolia API 单条 hit JSON 中提取标准化字段。
        字段缺失时使用安全默认值。
        """
        # title：优先 title，其次 story_title
        title = hit.get("title") or hit.get("story_title") or "无标题"

        # author
        author = hit.get("author") or "unknown"

        # points
        points = hit.get("points") or 0

        # comments_count
        comments_count = hit.get("num_comments") or 0

        # created_at：取 created_at 字段（ISO 格式），截取日期部分
        created_at_raw = hit.get("created_at", "")
        created_at = created_at_raw[:10] if created_at_raw else ""

        # url：优先 url 字段，其次用 objectID 拼接 HN 链接
        url = hit.get("url") or ""
        if not url:
            object_id = hit.get("objectID") or hit.get("story_id")
            if object_id:
                url = f"https://news.ycombinator.com/item?id={object_id}"

        return {
            "title": title,
            "author": author,
            "points": points,
            "comments_count": comments_count,
            "created_at": created_at,
            "url": url,
            "source": "hackernews",
        }

    def _columns(self) -> list:
        """DataFrame 标准列名。"""
        return [
            "title", "author", "points", "comments_count",
            "created_at", "url", "source",
        ]
