"""
collectors/base.py
所有采集器的抽象基类，定义统一接口。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import logging
import requests

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """
    采集器基类。
    子类需实现 collect() 方法，返回标准化的数据列表。
    """

    # 默认请求超时（秒）
    REQUEST_TIMEOUT = 15

    def __init__(self):
        self.session = requests.Session()

    @abstractmethod
    def collect(self, keyword: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        采集数据。

        Args:
            keyword: 搜索关键词
            days: 采集最近 N 天的数据

        Returns:
            标准化的数据条目列表，每条包含：
            - title: 标题
            - url: 链接
            - source: 来源（github / hackernews）
            - date: 日期字符串（YYYY-MM-DD）
            - score: 原始热度指标（star 数 / 评论数等）
            - description: 简要描述
        """
        pass

    def _safe_request(self, url: str, params: dict = None, headers: dict = None) -> dict | None:
        """
        带异常保护的 HTTP GET 请求。

        Returns:
            响应 JSON（成功时）或 None（失败时）
        """
        try:
            resp = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning(f"请求超时：{url}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP 错误：{e}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"请求异常：{e}")
        except ValueError:
            logger.warning(f"响应解析失败：{url}")
        return None
