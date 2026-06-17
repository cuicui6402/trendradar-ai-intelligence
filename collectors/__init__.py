"""
collectors 包
负责所有外部数据源的采集逻辑。
"""

from collectors.base import BaseCollector
from collectors.github_collector import GitHubCollector
from collectors.hn_collector import HNCollector

__all__ = ["BaseCollector", "GitHubCollector", "HNCollector"]
