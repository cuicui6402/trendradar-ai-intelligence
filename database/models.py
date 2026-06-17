"""
database/models.py
SQLAlchemy ORM 模型定义。
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


# ======================================================================
# 第 5 阶段：搜索历史模型
# ======================================================================

class SearchHistory(Base):
    """
    搜索历史记录。
    每次用户点击"开始分析"时写入一条。
    """
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(200), nullable=False, comment="搜索关键词")
    days = Column(Integer, nullable=False, default=30, comment="时间范围（天）")
    github_count = Column(Integer, default=0, comment="GitHub 结果数量")
    hn_count = Column(Integer, default=0, comment="Hacker News 结果数量")
    created_at = Column(DateTime, default=datetime.now, comment="搜索时间")

    # 关联
    github_results = relationship("GitHubResult", back_populates="search", cascade="all, delete-orphan")
    hn_results = relationship("HNResult", back_populates="search", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="search", cascade="all, delete-orphan")


class GitHubResult(Base):
    """
    GitHub 趋势评分结果。
    关联到 search_history，保存每次搜索的完整评分数据。
    """
    __tablename__ = "github_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("search_history.id"), nullable=False, comment="关联搜索记录")
    ranking = Column(Integer, default=0, comment="排名")
    repo_name = Column(String(500), default="", comment="仓库名")
    owner = Column(String(200), default="", comment="所有者")
    description = Column(Text, default="", comment="描述")
    stars = Column(Integer, default=0, comment="Star 数")
    forks = Column(Integer, default=0, comment="Fork 数")
    open_issues = Column(Integer, default=0, comment="Open Issue 数")
    language = Column(String(100), default="", comment="主要语言")
    created_at = Column(String(20), default="", comment="仓库创建时间")
    updated_at = Column(String(20), default="", comment="仓库更新时间")
    repo_url = Column(String(1000), default="", comment="仓库链接")
    trend_score = Column(Float, default=0.0, comment="趋势评分")

    # 关联
    search = relationship("SearchHistory", back_populates="github_results")


class HNResult(Base):
    """
    Hacker News 趋势评分结果。
    关联到 search_history，保存每次搜索的完整评分数据。
    """
    __tablename__ = "hn_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("search_history.id"), nullable=False, comment="关联搜索记录")
    ranking = Column(Integer, default=0, comment="排名")
    title = Column(String(500), default="", comment="帖子标题")
    author = Column(String(200), default="", comment="作者")
    points = Column(Integer, default=0, comment="Points")
    comments_count = Column(Integer, default=0, comment="评论数")
    created_at = Column(String(20), default="", comment="帖子创建时间")
    url = Column(String(1000), default="", comment="帖子链接")
    trend_score = Column(Float, default=0.0, comment="趋势评分")

    # 关联
    search = relationship("SearchHistory", back_populates="hn_results")


# ======================================================================
# 第 6 阶段：趋势报告模型
# ======================================================================

class Report(Base):
    """
    AI 趋势报告。
    关联到 search_history，保存每次生成的报告内容和文件路径。
    """
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("search_history.id"), nullable=False, comment="关联搜索记录")
    report_title = Column(String(500), default="", comment="报告标题")
    report_content = Column(Text, default="", comment="报告 Markdown 内容")
    markdown_path = Column(String(500), default="", comment="Markdown 文件保存路径")
    created_at = Column(DateTime, default=datetime.now, comment="报告生成时间")

    # 关联
    search = relationship("SearchHistory", back_populates="reports")


# ======================================================================
# 旧版模型（保留兼容性）
# ======================================================================

class TrendItem(Base):
    """
    采集到的单条趋势数据（旧版模型，保留兼容性）。
    """
    __tablename__ = "trend_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False, comment="标题")
    url = Column(String(1000), nullable=False, comment="链接")
    source = Column(String(50), nullable=False, comment="来源：github / hackernews")
    keyword = Column(String(200), nullable=False, comment="搜索关键词")
    date = Column(String(20), nullable=False, comment="数据日期 YYYY-MM-DD")
    score = Column(Float, default=0.0, comment="原始热度指标")
    trend_score = Column(Float, default=0.0, comment="计算后的趋势评分")
    description = Column(Text, default="", comment="简要描述")
    created_at = Column(DateTime, default=datetime.now, comment="记录创建时间")


class AnalysisRecord(Base):
    """
    一次完整的趋势分析记录（旧版模型，保留兼容性）。
    """
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(200), nullable=False, comment="分析关键词")
    time_range = Column(Integer, default=30, comment="时间范围（天）")
    total_items = Column(Integer, default=0, comment="采集到的数据条数")
    avg_score = Column(Float, default=0.0, comment="平均趋势评分")
    summary = Column(Text, default="", comment="分析摘要")
    report_path = Column(String(500), default="", comment="报告文件路径")
    created_at = Column(DateTime, default=datetime.now, comment="分析时间")
