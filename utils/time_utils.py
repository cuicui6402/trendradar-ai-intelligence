"""
utils/time_utils.py
时间相关的公共工具函数。
"""

from datetime import datetime, timedelta


def days_ago_str(days: int, fmt: str = "%Y-%m-%d") -> str:
    """
    返回 N 天前的日期字符串。

    Args:
        days: 天数偏移
        fmt: 日期格式

    Returns:
        格式化后的日期字符串
    """
    target = datetime.now() - timedelta(days=days)
    return target.strftime(fmt)


def parse_date(date_str: str, fmt: str = "%Y-%m-%d") -> datetime | None:
    """
    安全解析日期字符串。

    Args:
        date_str: 日期字符串
        fmt: 日期格式

    Returns:
        datetime 对象，解析失败时返回 None
    """
    try:
        return datetime.strptime(date_str, fmt)
    except (ValueError, TypeError):
        return None
