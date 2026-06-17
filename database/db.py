"""
database/db.py
SQLite 连接管理与会话工厂。
支持自动初始化：首次调用 get_session() 时自动创建表。
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from database.models import Base

logger = logging.getLogger(__name__)

# 默认数据库路径（项目根目录下）
DEFAULT_DB_PATH = "trendradar.db"

# 模块级状态：当前使用的数据库路径和初始化标志
_current_db_path = DEFAULT_DB_PATH
_initialized = False


def get_engine(db_path: str = None):
    """
    创建并返回 SQLAlchemy 引擎。

    Args:
        db_path: 数据库文件路径，默认使用当前模块记录的路径

    Returns:
        SQLAlchemy Engine 实例
    """
    if db_path is None:
        db_path = _current_db_path

    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=False)
    return engine


def get_session(db_path: str = None) -> Session:
    """
    创建并返回一个数据库会话。
    首次调用时自动执行 init_db()。

    Args:
        db_path: 数据库文件路径

    Returns:
        SQLAlchemy Session 实例
    """
    global _initialized
    if not _initialized:
        init_db(db_path)

    engine = get_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def init_db(db_path: str = None):
    """
    初始化数据库：创建所有表。
    如果表已存在则不重复创建。
    在 Streamlit 启动时调用，确保数据库就绪。

    Args:
        db_path: 数据库文件路径
    """
    global _initialized, _current_db_path
    if db_path is not None:
        _current_db_path = db_path
    engine = get_engine()
    Base.metadata.create_all(engine)
    _initialized = True
    logger.info(f"数据库表已初始化：{_current_db_path}")
