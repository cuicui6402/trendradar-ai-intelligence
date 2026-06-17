"""
services/report_service.py
报告生成与导出服务。

职责：
- 调用 TrendAgent 生成报告内容
- 将报告保存为 Markdown 文件到 data/reports/ 目录
- 返回文件路径供 app.py 展示和数据库记录
"""

import os
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from agent.trend_agent import TrendAgent

logger = logging.getLogger(__name__)


class ReportService:
    """
    将趋势分析结果生成为 Markdown 格式的报告文件。
    支持模板模式和 LLM 模式（由 TrendAgent 自动判断）。
    """

    # 报告文件保存目录（相对于项目根目录）
    REPORT_DIR = "data/reports"

    def __init__(self):
        """初始化报告服务和 TrendAgent。"""
        self.agent = TrendAgent()

    def generate_and_save(
        self, keyword: str, analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成报告并保存为 Markdown 文件。

        Args:
            keyword: 分析关键词
            analysis: 分析数据字典（包含 github_df, hn_df 等）

        Returns:
            结果字典，包含：
            - success: 是否成功
            - title: 报告标题
            - content: Markdown 报告正文
            - filepath: 文件保存路径
            - mode: 生成模式（"template" 或 "llm"）
            - error: 错误信息（失败时）
        """
        try:
            # 确定生成模式
            mode = "llm" if self.agent.is_available else "template"

            # 调用 Agent 生成报告
            content = self.agent.generate_report(keyword, analysis)

            # 生成标题
            today = datetime.now().strftime("%Y-%m-%d")
            title = "TrendRadar AI 趋势报告：" + keyword

            # 生成文件名并保存
            filename = self._make_filename(keyword)
            filepath = os.path.join(self.REPORT_DIR, filename)
            os.makedirs(self.REPORT_DIR, exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"报告已保存至：{filepath}（模式：{mode}）")

            return {
                "success": True,
                "title": title,
                "content": content,
                "filepath": filepath,
                "mode": mode,
            }

        except Exception as e:
            logger.error(f"报告生成失败：{e}")
            return {
                "success": False,
                "title": "",
                "content": "",
                "filepath": "",
                "mode": "",
                "error": str(e),
            }

    def _make_filename(self, keyword: str) -> str:
        """
        生成报告文件名。

        格式：trend_report_{keyword}_{YYYYMMDD}_{HHMMSS}.md
        对关键词中的特殊字符做安全处理。

        Args:
            keyword: 搜索关键词

        Returns:
            安全的文件名字符串
        """
        # 替换不安全字符
        safe_kw = re.sub(r'[^\w\u4e00-\u9fff-]', '_', keyword)
        # 截断过长的关键词
        if len(safe_kw) > 30:
            safe_kw = safe_kw[:30]

        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")
        filename = f"trend_report_{safe_kw}_{date_str}_{time_str}.md"
        return filename
