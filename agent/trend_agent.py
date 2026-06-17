"""
agent/trend_agent.py
趋势报告 Agent。

双模式运行：
- 模板模式（默认，无需 API Key）：基于规则生成结构化 9 章节 Markdown 报告
- LLM 模式（可选）：调用 OpenAI 兼容 API 生成深度分析报告

无论是否配置 LLM_API_KEY，用户都能获得可用的趋势报告。

v6.5 优化：
- GitHub 代表项目相关性评分（report_relevance_score），过滤资料类项目
- 当关键词包含 agent 时，报告各章节围绕 AI Agent 展开
"""

import os
import json
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

import pandas as pd
import requests

from agent.prompts import TREND_REPORT_SYSTEM, TREND_REPORT_USER

logger = logging.getLogger(__name__)


class TrendAgent:
    """
    基于 LLM 或规则模板的趋势分析 Agent。
    负责将结构化数据转化为面向求职、学习、技术调研的深度报告。
    """

    # ------------------------------------------------------------------
    # Agent 相关关键词集合（用于判断和匹配）
    # ------------------------------------------------------------------
    AGENT_KW_INDICATORS = ["agent", "agents", "智能体"]

    # repo_name / description 中出现以下词视为与 Agent 高度相关
    AGENT_RELATED_TERMS = [
        "agent", "agents", "ai", "llm", "workflow", "rag",
        "tool", "tools", "assistant", "automation",
        "autonomous", "copilot", "chain", "graph",
        "planning", "tool_use", "function_call",
        "langchain", "langgraph", "autogen", "crewai",
        "multi-agent", "agent framework",
    ]

    # owner / url 中出现以下词视为 AI/LLM 生态
    AGENT_ECOSYSTEM_OWNERS = [
        "langchain-ai", "openai", "anthropic", "microsoft",
        "google", "huggingface", "meta-llama", "deepseek",
        "crewai", "autogen", "llamaindex",
    ]

    # 资料类项目识别关键词（repo_name / owner / description 匹配）
    RESOURCE_TERMS = [
        "interview", "guide", "leetcode", "awesome",
        "collection", "roadmap", "cheatsheet", "tutorial-collection",
        "java-guide", "coding-interview",
    ]

    def __init__(self):
        """初始化 Agent，从环境变量读取 LLM 配置。"""
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self._available = bool(self.api_key)

        if self._available:
            logger.info("TrendAgent：LLM 已配置（model=" + self.model + "）")
        else:
            logger.info("TrendAgent：LLM_API_KEY 未配置，使用模板模式生成报告")

    @property
    def is_available(self) -> bool:
        """LLM API 是否已配置。"""
        return self._available

    # ==================================================================
    # 公共接口
    # ==================================================================

    def generate_report(self, keyword: str, analysis: Dict[str, Any]) -> str:
        """
        生成趋势分析报告。

        LLM 可用时调用 API 生成深度报告；
        LLM 不可用或调用失败时，回退到模板模式。
        """
        if not self._available:
            return self._generate_template_report(keyword, analysis)

        try:
            return self._generate_llm_report(keyword, analysis)
        except Exception as e:
            logger.warning("LLM 报告生成失败，回退到模板模式：" + str(e))
            return self._generate_template_report(keyword, analysis)

    # ==================================================================
    # 关键词检测
    # ==================================================================

    def _is_agent_keyword(self, keyword: str) -> bool:
        """
        判断关键词是否与 AI Agent 相关。

        Args:
            keyword: 用户输入的搜索关键词

        Returns:
            是否为 Agent 相关关键词
        """
        kw_lower = keyword.lower().strip()
        for indicator in self.AGENT_KW_INDICATORS:
            if indicator in kw_lower:
                return True
        return False

    # ==================================================================
    # 相关性评分与项目筛选
    # ==================================================================

    def _calculate_relevance_score(
        self, row: pd.Series, keyword: str
    ) -> float:
        """
        为单个 GitHub 项目计算报告相关性评分。
        用于在报告 Top5 中优先展示与关键词最相关的项目。

        评分规则：
        - repo_name 命中 Agent 相关词：每个 +3
        - description 命中 Agent 相关词：每个 +2
        - owner/url 属于 AI/LLM 生态：+1
        - 资料类项目（interview/guide/awesome 等）：-2
        - trend_score 归一化后作为辅助项（0-1）

        Args:
            row: DataFrame 行
            keyword: 搜索关键词

        Returns:
            相关性评分浮点数
        """
        score = 0.0
        repo_name = str(row.get("repo_name", "")).lower()
        owner = str(row.get("owner", "")).lower()
        desc = str(row.get("description", "")).lower()
        url = str(row.get("repo_url", "")).lower()

        is_agent = self._is_agent_keyword(keyword)

        if is_agent:
            # repo_name 命中相关词
            for term in self.AGENT_RELATED_TERMS:
                if term in repo_name:
                    score += 3

            # description 命中相关词
            for term in self.AGENT_RELATED_TERMS:
                if term in desc:
                    score += 2

            # owner/url 属于 AI 生态
            for eco_owner in self.AGENT_ECOSYSTEM_OWNERS:
                if eco_owner in owner or eco_owner in url:
                    score += 1
                    break

            # 资料类项目降权
            if self._is_resource_repo(row):
                score -= 2

        # trend_score 归一化作为辅助项
        trend_score = float(row.get("trend_score", 0))
        score += trend_score / 100.0

        return round(score, 2)

    def _is_resource_repo(self, row: pd.Series) -> bool:
        """
        判断项目是否为资料/集合/面试指南类项目。

        通用规则：当 repo_name、owner、description 中包含
        interview、guide、leetcode、awesome 等词时判定为资料类。

        Args:
            row: DataFrame 行

        Returns:
            是否为资料类项目
        """
        repo_name = str(row.get("repo_name", "")).lower()
        owner = str(row.get("owner", "")).lower()
        desc = str(row.get("description", "")).lower()

        for term in self.RESOURCE_TERMS:
            if term in repo_name or term in owner or term in desc:
                return True

        # "awesome-" 前缀的仓库通常是资料集合
        if repo_name.startswith("awesome-") or repo_name.startswith("awesome_"):
            return True

        return False

    def _get_report_top_projects(
        self, github_df: pd.DataFrame, keyword: str, top_n: int = 5
    ) -> pd.DataFrame:
        """
        为报告选取最相关的 Top N 项目。

        基于 report_relevance_score + trend_score 排序。
        当关键词为 Agent 相关时，资料类项目（interview/guide/awesome/leetcode）
        被硬过滤，不进入报告 Top N。

        Args:
            github_df: GitHub 评分后的 DataFrame
            keyword: 搜索关键词
            top_n: 返回项目数量

        Returns:
            筛选后的 DataFrame（最多 top_n 行）
        """
        if github_df is None or github_df.empty:
            return pd.DataFrame()

        is_agent = self._is_agent_keyword(keyword)
        df = github_df.copy()
        df["report_relevance_score"] = df.apply(
            lambda row: self._calculate_relevance_score(row, keyword), axis=1
        )

        # Agent 关键词时：硬过滤资料类项目（仅当剩余项目足够时）
        if is_agent:
            df["is_resource"] = df.apply(
                lambda row: self._is_resource_repo(row), axis=1
            )
            non_resource = df[df["is_resource"] == False]
            if len(non_resource) >= top_n:
                df = non_resource
            # 如果过滤后不足 top_n，保留所有非资料项目 + 部分资料项目
            # （此时资料项目排在末尾）
            else:
                df = pd.concat([
                    non_resource,
                    df[df["is_resource"] == True]
                ])

        # 综合排序：relevance + trend
        df["report_sort_score"] = (
            df["report_relevance_score"] + df["trend_score"] / 100.0
        )
        df = df.sort_values("report_sort_score", ascending=False)

        return df.head(top_n)

    # ==================================================================
    # 数据准备
    # ==================================================================

    def _prepare_context(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        从分析数据中提取报告生成所需的上下文信息。

        Args:
            analysis: 原始分析数据字典

        Returns:
            格式化后的上下文字典
        """
        github_df = analysis.get("github_df")
        hn_df = analysis.get("hn_df")
        keyword = analysis.get("keyword", "")

        # GitHub Top 项目文本（使用相关性筛选）
        github_top_text = "暂无 GitHub 数据"
        github_count = analysis.get("github_count", 0)
        github_avg_score = analysis.get("github_avg_score", 0)
        github_max_score = 0

        if github_df is not None and not github_df.empty:
            github_count = len(github_df)
            github_avg_score = round(float(github_df["trend_score"].mean()), 1)
            github_max_score = round(float(github_df["trend_score"].max()), 1)
            # 使用相关性筛选后的 Top 5
            top_items = self._get_report_top_projects(github_df, keyword, 5)
            lines = []
            for _, row in top_items.iterrows():
                repo = str(row.get("repo_name", ""))
                owner = str(row.get("owner", ""))
                stars = int(row.get("stars", 0))
                score = round(float(row.get("trend_score", 0)), 1)
                lang = str(row.get("language", "N/A"))
                desc = str(row.get("description", ""))[:80]
                lines.append(
                    "- " + owner + "/" + repo + ": " + str(stars)
                    + " stars, 趋势评分 " + str(score) + ", 语言 " + lang
                )
                if desc and desc != "nan":
                    lines.append("  描述：" + desc)
            github_top_text = "\n".join(lines)

        # HN Top 讨论文本
        hn_top_text = "暂无 Hacker News 数据"
        hn_count = analysis.get("hn_count", 0)
        hn_avg_score = analysis.get("hn_avg_score", 0)
        hn_max_score = 0

        if hn_df is not None and not hn_df.empty:
            hn_count = len(hn_df)
            hn_avg_score = round(float(hn_df["trend_score"].mean()), 1)
            hn_max_score = round(float(hn_df["trend_score"].max()), 1)
            top_items = hn_df.head(5)
            lines = []
            for _, row in top_items.iterrows():
                title = str(row.get("title", ""))[:60]
                points = int(row.get("points", 0))
                score = round(float(row.get("trend_score", 0)), 1)
                comments = int(row.get("comments_count", 0))
                lines.append(
                    "- " + title + ": " + str(points) + " points, "
                    + str(comments) + " comments, 趋势评分 " + str(score)
                )
            hn_top_text = "\n".join(lines)

        return {
            "github_count": github_count,
            "hn_count": hn_count,
            "github_avg_score": github_avg_score,
            "hn_avg_score": hn_avg_score,
            "github_max_score": github_max_score,
            "hn_max_score": hn_max_score,
            "github_top_text": github_top_text,
            "hn_top_text": hn_top_text,
        }

    # ==================================================================
    # 模板模式（无需 API Key）
    # ==================================================================

    def _generate_template_report(
        self, keyword: str, analysis: Dict[str, Any]
    ) -> str:
        """
        基于规则模板生成 9 章节结构化报告。
        当关键词包含 agent 时，各章节围绕 AI Agent 展开。
        """
        # 将 keyword 写入 analysis 供 _prepare_context 使用
        analysis["keyword"] = keyword

        ctx = self._prepare_context(analysis)
        today = datetime.now().strftime("%Y-%m-%d")
        days = analysis.get("days", 30)
        total = ctx["github_count"] + ctx["hn_count"]
        is_agent = self._is_agent_keyword(keyword)

        sections = []

        # ---- 标题 ----
        sections.append("# TrendRadar AI 趋势报告：" + keyword)
        sections.append("")
        sections.append(
            "> 生成日期：" + today + " | 时间范围：近 " + str(days)
            + " 天 | 数据总量：" + str(total) + " 条"
        )
        sections.append("")
        sections.append("---")
        sections.append("")

        # ---- 一、技术概览 ----
        sections.append("## 一、技术概览")
        sections.append("")
        if is_agent:
            sections.extend(self._section_tech_overview_agent(keyword, days, ctx))
        else:
            sections.extend(self._section_tech_overview_generic(keyword, days, ctx))
        sections.append("")

        # ---- 二、热度判断 ----
        sections.append("## 二、热度判断")
        sections.append("")
        sections.append(self._generate_heat_judgment(keyword, ctx, is_agent))
        sections.append("")

        # ---- 三、GitHub 热门项目解读 ----
        sections.append("## 三、GitHub 热门项目解读")
        sections.append("")
        github_df = analysis.get("github_df")
        if github_df is not None and not github_df.empty:
            top_gh = self._get_report_top_projects(github_df, keyword, 5)
            sections.extend(
                self._section_github_projects(top_gh, keyword, is_agent)
            )
        else:
            sections.append("暂无 GitHub 数据可供解读。")
            sections.append("")

        # ---- 四、HN 热门讨论分析 ----
        sections.append("## 四、Hacker News 热门讨论分析")
        sections.append("")
        hn_df = analysis.get("hn_df")
        if hn_df is not None and not hn_df.empty:
            sections.extend(
                self._section_hn_discussions(hn_df, keyword, is_agent)
            )
        else:
            sections.append("暂无 Hacker News 数据可供分析。")
            sections.append("")

        # ---- 五、典型业务场景 ----
        sections.append("## 五、典型业务场景")
        sections.append("")
        if is_agent:
            sections.extend(self._section_scenarios_agent(keyword))
        else:
            sections.extend(self._section_scenarios_generic(keyword))
        sections.append("")

        # ---- 六、国内生态建议 ----
        sections.append("## 六、国内生态建议")
        sections.append("")
        if is_agent:
            sections.extend(self._section_domestic_agent(keyword))
        else:
            sections.extend(self._section_domestic_generic(keyword))
        sections.append("")

        # ---- 七、求职项目推荐 ----
        sections.append("## 七、求职项目推荐")
        sections.append("")
        if is_agent:
            sections.extend(self._section_job_projects_agent(keyword))
        else:
            sections.extend(
                self._section_job_projects_generic(keyword, analysis)
            )
        sections.append("")

        # ---- 八、面试常见问题 ----
        sections.append("## 八、面试常见问题")
        sections.append("")
        if is_agent:
            sections.extend(self._section_interview_agent(keyword))
        else:
            sections.extend(self._section_interview_generic(keyword))
        sections.append("")

        # ---- 九、学习路径建议 ----
        sections.append("## 九、学习路径建议")
        sections.append("")
        if is_agent:
            sections.extend(self._section_learning_agent(keyword, analysis))
        else:
            sections.extend(self._section_learning_generic(keyword, analysis))
        sections.append("")

        # ---- 页脚 ----
        sections.append("---")
        sections.append("")
        sections.append(
            "*本报告由 TrendRadar 基于规则模板自动生成，数据仅供参考。"
            "配置 LLM_API_KEY 后可获得 AI 深度分析报告。*"
        )

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 一、技术概览
    # ------------------------------------------------------------------

    def _section_tech_overview_agent(
        self, keyword: str, days: int, ctx: Dict[str, Any]
    ) -> List[str]:
        """AI Agent 专属技术概览。"""
        lines = []
        lines.append(
            "**AI Agent** 不是普通的聊天机器人，而是具备**任务规划、工具调用、"
            "记忆管理、外部数据访问和多步骤执行**能力的智能系统。"
            "与传统的 LLM 问答不同，Agent 能够自主分解复杂任务、调用外部 API "
            "和工具、维护上下文状态，并根据中间结果动态调整执行策略。"
        )
        lines.append("")
        lines.append(
            "本次分析围绕「" + keyword + "」展开，覆盖了近 " + str(days)
            + " 天内的 GitHub 仓库数据和 Hacker News 社区讨论数据。"
        )
        lines.append("")

        gh_count = ctx["github_count"]
        hn_count = ctx["hn_count"]

        if gh_count > 0 and hn_count > 0:
            lines.append(
                "共采集到 " + str(gh_count) + " 个 GitHub 相关仓库和 "
                + str(hn_count) + " 条 Hacker News 讨论，"
                "表明 AI Agent 在开源社区和技术媒体上均有高度关注。"
            )
        elif gh_count > 0:
            lines.append(
                "共采集到 " + str(gh_count) + " 个 GitHub 相关仓库，"
                "AI Agent 方向在开源社区非常活跃。"
            )
        elif hn_count > 0:
            lines.append(
                "Hacker News 上有 " + str(hn_count) + " 条关于 AI Agent 的讨论。"
            )
        else:
            lines.append("当前时间范围内未采集到有效数据。")

        return lines

    def _section_tech_overview_generic(
        self, keyword: str, days: int, ctx: Dict[str, Any]
    ) -> List[str]:
        """通用技术概览。"""
        lines = []
        lines.append(
            "本次分析围绕「" + keyword + "」展开，覆盖了近 " + str(days)
            + " 天内的 GitHub 仓库数据和 Hacker News 社区讨论数据。"
        )
        lines.append("")

        gh_count = ctx["github_count"]
        hn_count = ctx["hn_count"]

        if gh_count > 0 and hn_count > 0:
            lines.append(
                "共采集到 " + str(gh_count) + " 个 GitHub 相关仓库和 "
                + str(hn_count) + " 条 Hacker News 讨论，"
                "表明该技术在开源社区和技术媒体上均有一定关注度。"
            )
        elif gh_count > 0:
            lines.append(
                "共采集到 " + str(gh_count) + " 个 GitHub 相关仓库，"
                "该技术在开源社区有一定存在感，但 Hacker News 上的讨论较少。"
            )
        elif hn_count > 0:
            lines.append(
                "GitHub 上未找到直接相关仓库，但 Hacker News 上有 "
                + str(hn_count) + " 条讨论，"
                "表明该技术可能处于早期讨论阶段或以非开源形式存在。"
            )
        else:
            lines.append(
                "当前时间范围内未采集到有效数据，"
                "可能原因包括：技术过于新众、关键词拼写有误或 API 访问受限。"
            )

        return lines

    # ------------------------------------------------------------------
    # 二、热度判断（增强 Agent 版）
    # ------------------------------------------------------------------

    def _generate_heat_judgment(
        self, keyword: str, ctx: Dict[str, Any], is_agent: bool = False
    ) -> str:
        """
        根据数据指标生成热度判断文本。
        Agent 模式下会额外关注安全、成本、编程 Agent 等高关注话题。
        """
        gh_count = ctx["github_count"]
        hn_count = ctx["hn_count"]
        gh_avg = ctx["github_avg_score"]
        hn_avg = ctx["hn_avg_score"]
        total = gh_count + hn_count

        lines = []

        lines.append("- GitHub 相关仓库数：" + str(gh_count))
        lines.append("- Hacker News 讨论数：" + str(hn_count))
        if gh_count > 0:
            lines.append("- GitHub 平均趋势评分：" + str(gh_avg))
        if hn_count > 0:
            lines.append("- HN 平均趋势评分：" + str(hn_avg))
        lines.append("")

        if total >= 30:
            lines.append(
                "**综合判断：「" + keyword + "」当前热度较高。**"
            )
            lines.append("")
            lines.append(
                "该技术在 GitHub 和 Hacker News 上均有较多近期活动和讨论，"
                "表明社区关注度较高，处于活跃发展阶段。"
                "对于求职者来说，这是一个值得投入时间的方向。"
            )
        elif total >= 15:
            lines.append(
                "**综合判断：「" + keyword + "」当前热度中等偏上。**"
            )
            lines.append("")
            lines.append(
                "该技术有一定的社区基础，但尚未成为主流热门方向。"
                "建议持续关注其发展动态，如果呈现上升趋势则值得提前布局。"
            )
        elif total >= 5:
            lines.append(
                "**综合判断：「" + keyword + "」当前热度一般。**"
            )
            lines.append("")
            lines.append(
                "该技术的社区讨论和开源活动相对较少，"
                "可能处于早期发展阶段或属于较垂直的技术领域。"
                "建议结合个人兴趣和目标岗位需求决定是否深入学习。"
            )
        else:
            lines.append(
                "**综合判断：「" + keyword + "」当前热度较低。**"
            )
            lines.append("")
            lines.append(
                "近期在 GitHub 和 Hacker News 上的相关数据较少，"
                "可能是过于新众、关键词拼写有误，或该技术目前关注度不高。"
                "建议核实关键词后重新搜索，或尝试使用英文关键词。"
            )

        # Agent 模式：补充高关注话题
        if is_agent and hn_count > 0:
            lines.append("")
            lines.append(
                "**HN 社区高关注话题：** 近期 AI Agent 领域的热点讨论集中在"
                " Agent 安全与失控风险、工具调用权限控制、LLM 调用成本优化、"
                "编程 Agent（如 Cursor/Copilot）的实用化进展、"
                "Guardrails 与合规审计、以及金融/银行场景的安全部署等方向。"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 三、GitHub 热门项目解读
    # ------------------------------------------------------------------

    def _section_github_projects(
        self, top_gh: pd.DataFrame, keyword: str, is_agent: bool
    ) -> List[str]:
        """生成 GitHub 项目解读章节。"""
        lines = []
        if is_agent:
            lines.append(
                "以下为经过相关性筛选的 AI Agent 代表项目（按 "
                "report_relevance_score + trend_score 排序）："
            )
            lines.append("")

        for _, row in top_gh.iterrows():
            repo = str(row.get("repo_name", ""))
            owner = str(row.get("owner", ""))
            stars = int(row.get("stars", 0))
            forks = int(row.get("forks", 0))
            score = round(float(row.get("trend_score", 0)), 1)
            lang = str(row.get("language", "N/A"))
            desc = str(row.get("description", ""))
            if len(desc) > 120:
                desc = desc[:120] + "..."
            url = str(row.get("repo_url", ""))

            lines.append("### " + owner + "/" + repo)
            lines.append("")
            lines.append(
                "- Stars: " + str(stars) + " | Forks: " + str(forks)
                + " | 语言: " + lang + " | 趋势评分: " + str(score)
            )
            if desc and desc != "nan":
                lines.append("- 描述: " + desc)
            if url:
                lines.append("- 链接: " + url)

            # Agent 模式：补充与 Agent 的关系和学习价值
            if is_agent:
                lines.append(
                    "- **与 AI Agent 的关系**: "
                    + self._infer_agent_relation(repo, desc)
                )
                lines.append(
                    "- **适合学习**: "
                    + self._infer_learning_value(repo, desc, lang)
                )

            lines.append("")

        return lines

    def _infer_agent_relation(self, repo: str, desc: str) -> str:
        """根据仓库名和描述推断与 AI Agent 的关系。"""
        combined = (repo + " " + desc).lower()

        if "langgraph" in combined or "graph" in combined:
            return "提供有状态的多 Agent 编排和工作流图引擎"
        if "langchain" in combined or "chain" in combined:
            return "LLM 应用开发框架，Agent 工具链的基础设施"
        if "autogen" in combined or "multi-agent" in combined:
            return "多 Agent 协作框架，支持 Agent 间的对话与任务分配"
        if "crew" in combined:
            return "多 Agent 团队协作框架，角色化分工执行复杂任务"
        if "rag" in combined or "retrieval" in combined:
            return "RAG 检索增强生成，Agent 获取外部知识的核心能力"
        if "tool" in combined or "function" in combined:
            return "工具调用与函数调用能力，Agent 与外部系统交互的接口"
        if "agent" in combined:
            return "Agent 框架或工具，提供自主任务规划和执行能力"
        if "workflow" in combined or "automation" in combined:
            return "工作流自动化，可用于 Agent 的任务编排和执行"
        if "assistant" in combined or "copilot" in combined:
            return "AI 助手类产品，Agent 的典型应用形态"
        return "可关注其在 AI Agent 生态中的定位和集成方式"

    def _infer_learning_value(self, repo: str, desc: str, lang: str) -> str:
        """根据仓库信息推断学习价值。"""
        combined = (repo + " " + desc).lower()

        if "langgraph" in combined or "graph" in combined:
            return "有状态 Agent 工作流设计、节点编排、条件路由"
        if "langchain" in combined or "chain" in combined:
            return "LLM 应用开发模式、Chain 组合、Tool 集成"
        if "autogen" in combined or "multi-agent" in combined:
            return "多 Agent 协作模式、对话式任务分解"
        if "rag" in combined or "retrieval" in combined:
            return "向量检索、文档切分、检索策略优化"
        if "tool" in combined or "function" in combined:
            return "Tool Calling 实现、函数注册与调度"
        if "agent" in combined:
            return "Agent 架构设计、任务规划、工具调用链路"
        return "了解该项目的架构设计和在 Agent 系统中的集成方式"

    # ------------------------------------------------------------------
    # 四、HN 讨论分析
    # ------------------------------------------------------------------

    def _section_hn_discussions(
        self, hn_df: pd.DataFrame, keyword: str, is_agent: bool
    ) -> List[str]:
        """生成 HN 讨论分析章节。"""
        lines = []
        top_hn = hn_df.head(5)

        for _, row in top_hn.iterrows():
            title = str(row.get("title", ""))
            points = int(row.get("points", 0))
            comments = int(row.get("comments_count", 0))
            score = round(float(row.get("trend_score", 0)), 1)
            url = str(row.get("url", ""))

            lines.append("### " + title)
            lines.append("")
            lines.append(
                "- Points: " + str(points) + " | 评论: " + str(comments)
                + " | 趋势评分: " + str(score)
            )
            if url and url != "nan":
                lines.append("- 链接: " + url)

            # Agent 模式：总结讨论关注点
            if is_agent:
                lines.append(
                    "- **关注点**: "
                    + self._infer_hn_focus(title, points, comments)
                )

            lines.append("")

        # 讨论趋势总结
        avg_points = int(hn_df["points"].mean())
        avg_comments = int(hn_df["comments_count"].mean())

        if is_agent:
            lines.append(
                "综合来看，HN 社区关于 AI Agent 的讨论平均获得 "
                + str(avg_points) + " Points 和 " + str(avg_comments)
                + " 条评论。"
            )
            lines.append("")
            lines.append(
                "社区讨论热点集中在 Agent 失控风险、工具调用权限边界、"
                "LLM 调用成本控制、编程 Agent 的实际效果、"
                "Guardrails 安全机制、以及金融/银行场景的安全部署等方面。"
                "高评论数帖子往往涉及 Agent 安全与成本话题。"
            )
        else:
            lines.append(
                "综合来看，HN 社区关于「" + keyword + "」的讨论平均获得 "
                + str(avg_points) + " Points 和 " + str(avg_comments)
                + " 条评论，表明社区对该话题有一定讨论深度。"
            )

        return lines

    def _infer_hn_focus(
        self, title: str, points: int, comments: int
    ) -> str:
        """根据 HN 帖子标题推断讨论关注点。"""
        t = title.lower()

        if "risk" in t or "danger" in t or "unsafe" in t or "失控" in t:
            return "Agent 失控风险与安全控制"
        if "cost" in t or "expensive" in t or "pricing" in t:
            return "LLM 调用成本与资源优化"
        if "security" in t or "bank" in t or "financial" in t:
            return "金融/安全场景的 Agent 部署"
        if "guardrail" in t or "permission" in t or "audit" in t:
            return "Agent 权限控制与审计机制"
        if "coding" in t or "programmer" in t or "cursor" in t or "copilot" in t:
            return "编程 Agent 的实用化进展"
        if "local" in t or "self-host" in t or "privacy" in t:
            return "本地 Agent 部署与隐私保护"
        if "automat" in t or "workflow" in t:
            return "自动化 Agent 与工作流集成"
        if "rag" in t or "retrieval" in t or "knowledge" in t:
            return "RAG 知识库与检索增强"
        if comments > 50:
            return "高关注度讨论，可能涉及 Agent 安全、成本或实用化争议"
        return "Agent 技术讨论与实践分享"

    # ------------------------------------------------------------------
    # 五、典型业务场景
    # ------------------------------------------------------------------

    def _section_scenarios_agent(self, keyword: str) -> List[str]:
        """AI Agent 专属业务场景。"""
        lines = []
        lines.append(
            "以下是 AI Agent 技术的典型落地场景，"
            "每个场景均可作为简历项目的选题方向："
        )
        lines.append("")
        lines.append(
            "1. **智能客服与工单分流**：Agent 自动理解用户意图，"
            "调用知识库检索答案，无法解决时自动转人工并附上上下文摘要。"
        )
        lines.append(
            "2. **企业知识库 / RAG 问答**：基于企业文档构建向量索引，"
            "Agent 接收自然语言问题后检索相关段落并生成结构化回答。"
        )
        lines.append(
            "3. **自动化数据分析 Agent**：用户上传 CSV 后，"
            "Agent 自动分析数据特征、生成可视化图表并输出分析报告。"
        )
        lines.append(
            "4. **技术情报 / 趋势监控 Agent**：定时采集 GitHub、HN、"
            "技术博客数据，Agent 计算趋势评分并生成周报推送。"
        )
        lines.append(
            "5. **编程助手 / 代码审查 Agent**：Agent 分析代码变更，"
            "检查代码规范、潜在 Bug 和安全漏洞，给出修改建议。"
        )
        lines.append(
            "6. **运营日报与自动报告生成**：Agent 从数据库和 API "
            "拉取业务指标，自动生成日报/周报并发送到 IM 群。"
        )
        lines.append(
            "7. **办公流程自动化**：Agent 串联邮件、日历、文档等工具，"
            "自动执行会议安排、信息汇总、文件归档等重复性任务。"
        )
        return lines

    def _section_scenarios_generic(self, keyword: str) -> List[str]:
        """通用业务场景。"""
        lines = []
        lines.append(
            "基于当前数据分析，以下是「" + keyword + "」可能的典型应用场景："
        )
        lines.append("")
        lines.append(
            "1. **Web 应用/服务开发**：适合构建面向用户的互联网产品，"
            "特别是需要快速迭代和灵活架构的场景。"
        )
        lines.append(
            "2. **内部工具与自动化**：用于构建企业内部效率工具、"
            "自动化流水线或数据处理管道。"
        )
        lines.append(
            "3. **数据处理与分析**：适用于数据清洗、转换、"
            "分析等场景，尤其是需要与多种数据源集成的情况。"
        )
        lines.append(
            "4. **AI/LLM 应用集成**：如果该技术涉及 AI 生态，"
            "可用于构建智能助手、RAG 系统、Agent 工作流等应用。"
        )
        lines.append(
            "5. **开源社区贡献**：参与相关开源项目开发，"
            "积累技术影响力和社区声誉。"
        )
        return lines

    # ------------------------------------------------------------------
    # 六、国内生态建议
    # ------------------------------------------------------------------

    def _section_domestic_agent(self, keyword: str) -> List[str]:
        """AI Agent 专属国内生态建议。"""
        lines = []
        lines.append(
            "AI Agent 在国内的落地需要特别关注以下方面："
        )
        lines.append("")
        lines.append(
            "1. **国产模型适配**：优先考虑 DeepSeek、通义千问、Kimi "
            "等国产大模型的 API 兼容性和调用稳定性，"
            "降低对 OpenAI 的依赖风险。"
        )
        lines.append(
            "2. **LLM 调用成本控制**：国内项目对成本敏感，"
            "需要设计缓存策略（相似问题复用）、降级策略（简单问题用小模型）、"
            "以及 Token 用量监控。"
        )
        lines.append(
            "3. **私有化部署与数据安全**：企业场景下，Agent 可能需要访问"
            "内部系统，需支持本地部署或通过内网 API 调用，"
            "确保敏感数据不外传。"
        )
        lines.append(
            "4. **中文语义理解**：国产模型在中文场景下有优势，"
            "但 Tool Calling 的函数名和参数通常需要英文，"
            "需要做好中英文映射。"
        )
        lines.append(
            "5. **工具调用权限边界**：Agent 调用外部工具（发邮件、"
            "操作数据库、修改配置）必须有明确的权限白名单，"
            "高风险操作需要人工确认。"
        )
        lines.append(
            "6. **日志审计与异常回滚**：所有 Agent 的工具调用和决策"
            "必须记录完整日志，异常操作应支持回滚和告警。"
        )
        lines.append(
            "7. **API 稳定性与降级策略**：国内 LLM API 偶有不稳定，"
            "需要实现多模型 fallback、超时重试和本地缓存兜底。"
        )
        return lines

    def _section_domestic_generic(self, keyword: str) -> List[str]:
        """通用国内生态建议。"""
        lines = []
        lines.append(
            "关于「" + keyword + "」在国内的发展情况，以下是一些参考建议："
        )
        lines.append("")
        lines.append(
            "- 建议关注国内主流技术社区（如掘金、知乎技术专栏、InfoQ）"
            "上关于该技术的实践分享。"
        )
        lines.append(
            "- 检查是否有国内团队维护的相关开源项目或中文文档翻译。"
        )
        lines.append(
            "- 关注国内大厂（阿里、字节、腾讯、百度等）是否在该领域有布局，"
            "这通常意味着该技术在国内的落地前景。"
        )
        lines.append(
            "- 如果该技术涉及 AI 领域，建议关注国内的替代方案和适配生态。"
        )
        return lines

    # ------------------------------------------------------------------
    # 七、求职项目推荐
    # ------------------------------------------------------------------

    def _section_job_projects_agent(self, keyword: str) -> List[str]:
        """AI Agent 专属求职项目推荐。"""
        lines = []
        lines.append(
            "以下是面向 AI Agent 方向的具体简历项目推荐，"
            "每个项目都包含核心功能、技术栈和求职能力说明："
        )
        lines.append("")

        lines.append("### 1. DataInsight Agent：智能数据分析与报告生成平台")
        lines.append("")
        lines.append(
            "- **核心功能**：用户上传 CSV/Excel 文件，Agent 自动分析数据特征，"
            "生成可视化图表和分析报告，支持自然语言追问。"
        )
        lines.append(
            "- **技术栈**：Python + Streamlit + LangChain/LangGraph + "
            "Pandas + Plotly + LLM API"
        )
        lines.append(
            "- **求职能力**：展示 Agent 任务规划、Tool Calling（数据分析工具）、"
            "多轮对话和数据处理能力。"
        )
        lines.append("")

        lines.append("### 2. JobPilot：简历-JD 匹配与面试准备 Agent")
        lines.append("")
        lines.append(
            "- **核心功能**：用户输入目标岗位 JD，Agent 分析简历匹配度，"
            "生成针对性面试准备材料（常见问题、项目讲解话术、技术知识点）。"
        )
        lines.append(
            "- **技术栈**：Python + RAG + 向量数据库 + LLM API + FastAPI"
        )
        lines.append(
            "- **求职能力**：展示 RAG 检索增强、知识库构建、"
            "Agent 多工具协作和工程化部署能力。"
        )
        lines.append("")

        lines.append("### 3. TrendRadar：技术趋势情报分析 Agent")
        lines.append("")
        lines.append(
            "- **核心功能**：定时采集 GitHub 和 HN 数据，Agent 计算趋势评分，"
            "生成面向求职和技术调研的分析报告，支持定时推送。"
        )
        lines.append(
            "- **技术栈**：Python + Streamlit + SQLite + Plotly + "
            "Requests + LLM API"
        )
        lines.append(
            "- **求职能力**：展示数据采集、评分模型设计、"
            "Agent 报告生成和定时任务调度能力。"
        )
        lines.append("")

        lines.append("### 4. TicketFlow：智能客服工单处理 Agent")
        lines.append("")
        lines.append(
            "- **核心功能**：Agent 自动分类用户工单，调用知识库回答常见问题，"
            "复杂问题自动转人工并附上上下文摘要和处理建议。"
        )
        lines.append(
            "- **技术栈**：Python + RAG + LLM API + FastAPI + "
            "消息队列（Redis/RabbitMQ）"
        )
        lines.append(
            "- **求职能力**：展示 Agent 意图识别、工具调用、"
            "人机协作流程设计和生产级系统设计能力。"
        )
        lines.append("")

        lines.append("### 5. StudyMate：课程资料 RAG 问答与复习 Agent")
        lines.append("")
        lines.append(
            "- **核心功能**：上传课程 PDF/PPT，Agent 构建知识库，"
            "支持自然语言问答、知识点总结和模拟考试生成。"
        )
        lines.append(
            "- **技术栈**：Python + LangChain + 向量数据库 + "
            "PDF 解析 + LLM API + Streamlit"
        )
        lines.append(
            "- **求职能力**：展示文档处理、RAG Pipeline 设计、"
            "Agent 多工具编排和产品化能力。"
        )

        return lines

    def _section_job_projects_generic(
        self, keyword: str, analysis: Dict[str, Any]
    ) -> List[str]:
        """通用求职项目推荐。"""
        lines = []
        lines.append(
            "以下是基于「" + keyword + "」趋势数据推荐的简历项目方向："
        )
        lines.append("")

        github_df = analysis.get("github_df")
        if github_df is not None and not github_df.empty and len(github_df) > 0:
            top_repo = str(github_df.iloc[0].get("repo_name", "相关框架"))
            lines.append(
                "1. **全栈应用项目**：使用 " + top_repo + " 构建一个完整的 "
                "Web 应用，包含前端、后端 API 和数据库。"
                "展示你的全栈开发能力和对主流框架的掌握。"
            )
            lines.append("")
            lines.append(
                "2. **自动化/效率工具**：基于 " + keyword + " 技术栈开发一个"
                "解决实际问题的小工具（如 CLI 工具、浏览器插件、自动化脚本）。"
                "展示你的工程能力和产品思维。"
            )
            lines.append("")
            lines.append(
                "3. **数据分析/可视化项目**：利用 " + keyword + " 相关技术"
                "构建数据分析 Pipeline，包含数据采集、清洗、分析和可视化。"
                "展示你的数据处理能力。"
            )
        else:
            lines.append(
                "1. **基础 CRUD 应用**：使用 " + keyword + " 相关技术构建一个"
                "包含增删改查功能的应用，展示基本开发能力。"
            )
            lines.append("")
            lines.append(
                "2. **API 服务项目**：构建一个 RESTful API 服务，"
                "展示后端开发和接口设计能力。"
            )
            lines.append("")
            lines.append(
                "3. **开源贡献**：参与 " + keyword + " 相关开源项目的 "
                "Issue 修复或功能开发，展示协作能力。"
            )
        return lines

    # ------------------------------------------------------------------
    # 八、面试常见问题
    # ------------------------------------------------------------------

    def _section_interview_agent(self, keyword: str) -> List[str]:
        """AI Agent 专属面试问题。"""
        lines = []
        lines.append(
            "以下是 AI Agent 方向的常见面试问题及回答要点："
        )
        lines.append("")

        questions = [
            (
                "Agent 和普通 LLM 聊天机器人的区别是什么？",
                "回答要点：Agent 具备任务规划、工具调用、记忆管理和多步骤执行能力，"
                "而普通聊天机器人只做单轮或多轮问答，不会主动调用外部系统。"
            ),
            (
                "Tool Calling 失败时如何处理？",
                "回答要点：实现重试机制（指数退避）、fallback 到替代工具、"
                "记录失败日志、通知用户并请求人工干预。"
            ),
            (
                "Agent 如何做任务规划？",
                "回答要点：将复杂任务分解为子任务，确定执行顺序和依赖关系，"
                "根据中间结果动态调整计划。常见模式：ReAct、Plan-and-Execute。"
            ),
            (
                "如何避免 Agent 无限循环或越权调用工具？",
                "回答要点：设置最大执行步数、工具调用白名单、"
                "高风险操作人工确认、循环检测（重复状态判断）和超时终止。"
            ),
            (
                "RAG 和 Agent 是什么关系？",
                "回答要点：RAG 是 Agent 获取外部知识的一种工具。"
                "Agent 负责规划和决策，RAG 负责从知识库中检索相关信息供 Agent 使用。"
            ),
            (
                "如何做 Agent 日志审计和安全控制？",
                "回答要点：记录每次工具调用的输入输出、LLM 的推理过程、"
                "用户指令和最终结果。安全控制包括权限分级、敏感操作审批、"
                "异常告警和操作回滚。"
            ),
            (
                "如何控制 LLM 调用成本？",
                "回答要点：实现语义缓存（相似问题复用回答）、"
                "模型分级（简单问题用小模型）、Token 用量监控、"
                "Prompt 精简、批量处理。"
            ),
            (
                "你项目中的 Agent 具体调用了哪些工具？",
                "回答要点：结合具体项目经验，说明工具的设计目的、"
                "调用时机、参数格式和错误处理方式。"
            ),
        ]

        for i, (q, a) in enumerate(questions, 1):
            lines.append(str(i) + ". **" + q + "**  ")
            lines.append("   " + a)
            lines.append("")

        return lines

    def _section_interview_generic(self, keyword: str) -> List[str]:
        """通用面试问题。"""
        lines = []
        lines.append(
            "以下是与「" + keyword + "」相关的常见面试问题及回答要点："
        )
        lines.append("")
        lines.append(
            "1. **请介绍一下 " + keyword + " 的核心概念和优势？**  \n"
            "   回答要点：从设计哲学、核心特性、与同类技术对比等角度回答。"
        )
        lines.append("")
        lines.append(
            "2. **" + keyword + " 的架构设计是怎样的？**  \n"
            "   回答要点：描述其核心组件、数据流和模块间的交互关系。"
        )
        lines.append("")
        lines.append(
            "3. **在实际项目中，你如何使用 " + keyword + "？**  \n"
            "   回答要点：结合具体项目经验，说明使用场景和遇到的问题。"
        )
        lines.append("")
        lines.append(
            "4. **" + keyword + " 的性能优化有哪些常见手段？**  \n"
            "   回答要点：从缓存、异步处理、并发、资源管理等角度展开。"
        )
        lines.append("")
        lines.append(
            "5. **" + keyword + " 与其他类似技术相比有什么异同？**  \n"
            "   回答要点：从功能、性能、生态、学习曲线等维度对比。"
        )
        lines.append("")
        lines.append(
            "6. **如何处理 " + keyword + " 中的错误和异常？**  \n"
            "   回答要点：描述错误处理策略、日志方案和重试机制。"
        )
        return lines

    # ------------------------------------------------------------------
    # 九、学习路径建议
    # ------------------------------------------------------------------

    def _section_learning_agent(
        self, keyword: str, analysis: Dict[str, Any]
    ) -> List[str]:
        """AI Agent 专属学习路径（四阶段）。"""
        lines = []
        lines.append("以下是 AI Agent 方向的四阶段学习路径：")
        lines.append("")

        lines.append(
            "**阶段一：入门（1-2 周）**  \n"
            "- 学习 LLM API 调用（OpenAI / DeepSeek / 通义千问）  \n"
            "- 掌握 Prompt Engineering 基本技巧  \n"
            "- 理解 JSON 结构化输出  \n"
            "- 学习 Function Calling / Tool Use 的基本概念"
        )
        lines.append("")

        lines.append(
            "**阶段二：进阶（2-4 周）**  \n"
            "- 深入 Tool Calling：工具注册、参数解析、错误处理  \n"
            "- 学习 RAG：文档切分、向量数据库、检索策略  \n"
            "- 理解任务规划模式：ReAct、Plan-and-Execute  \n"
            "- 阅读 LangChain / LangGraph 等框架源码"
        )
        lines.append("")

        lines.append(
            "**阶段三：工程化（2-4 周）**  \n"
            "- 用 Streamlit / FastAPI 构建 Web 界面和 API 服务  \n"
            "- 设计数据库存储（搜索历史、对话记录、工具调用日志）  \n"
            "- 实现日志系统、异常处理和权限控制  \n"
            "- 学习成本控制：缓存、降级、Token 监控"
        )
        lines.append("")

        lines.append(
            "**阶段四：项目实战（1-2 个月）**  \n"
            "- 选择一个方向（如 DataInsight Agent 或 TrendRadar）做一个可演示的系统  \n"
            "- 整理 README（包含架构图、技术栈、运行截图）  \n"
            "- 准备面试讲解稿（项目背景、技术选型、核心实现、遇到的挑战）  \n"
            "- 部署上线，提供在线演示链接"
        )
        lines.append("")

        # 推荐学习资源（使用相关性筛选后的 Top 项目）
        github_df = analysis.get("github_df")
        if github_df is not None and not github_df.empty:
            top_gh = self._get_report_top_projects(github_df, keyword, 3)
            if not top_gh.empty:
                lines.append("**推荐学习资源：**")
                for _, row in top_gh.iterrows():
                    repo = str(row.get("repo_name", ""))
                    owner = str(row.get("owner", ""))
                    url = str(row.get("repo_url", ""))
                    stars = int(row.get("stars", 0))
                    lines.append(
                        "- [" + owner + "/" + repo + "]("
                        + url + ") (" + str(stars) + " stars)"
                    )
                lines.append("")

        return lines

    def _section_learning_generic(
        self, keyword: str, analysis: Dict[str, Any]
    ) -> List[str]:
        """通用学习路径（三阶段）。"""
        lines = []
        lines.append("以下是学习「" + keyword + "」的建议路径：")
        lines.append("")
        lines.append(
            "**入门阶段（1-2 周）**  \n"
            "- 阅读官方文档的 Quick Start 或 Tutorial  \n"
            "- 完成一个 Hello World 级别的小项目  \n"
            "- 理解核心概念和基本 API"
        )
        lines.append("")
        lines.append(
            "**进阶阶段（2-4 周）**  \n"
            "- 深入学习高级特性和配置选项  \n"
            "- 阅读优秀开源项目的源码  \n"
            "- 尝试解决实际问题"
        )
        lines.append("")
        lines.append(
            "**实战阶段（1-2 个月）**  \n"
            "- 构建一个完整的简历项目  \n"
            "- 参与开源社区贡献  \n"
            "- 撰写技术博客分享学习心得"
        )
        lines.append("")

        github_df = analysis.get("github_df")
        if github_df is not None and not github_df.empty:
            lines.append("**推荐学习资源：**")
            top_3 = github_df.head(3)
            for _, row in top_3.iterrows():
                repo = str(row.get("repo_name", ""))
                owner = str(row.get("owner", ""))
                url = str(row.get("repo_url", ""))
                stars = int(row.get("stars", 0))
                lines.append(
                    "- [" + owner + "/" + repo + "]("
                    + url + ") (" + str(stars) + " stars)"
                )
            lines.append("")

        return lines

    # ==================================================================
    # LLM 模式（需要 API Key）
    # ==================================================================

    def _generate_llm_report(
        self, keyword: str, analysis: Dict[str, Any]
    ) -> str:
        """
        调用 OpenAI 兼容 API 生成深度趋势报告。
        """
        analysis["keyword"] = keyword
        ctx = self._prepare_context(analysis)

        user_prompt = TREND_REPORT_USER.format(
            keyword=keyword,
            github_count=ctx["github_count"],
            github_avg_score=ctx["github_avg_score"],
            github_max_score=ctx["github_max_score"],
            github_top_text=ctx["github_top_text"],
            hn_count=ctx["hn_count"],
            hn_avg_score=ctx["hn_avg_score"],
            hn_max_score=ctx["hn_max_score"],
            hn_top_text=ctx["hn_top_text"],
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": TREND_REPORT_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 4000,
        }

        base_url = self.base_url.rstrip("/")
        url = base_url + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }

        result = self._safe_request(url, headers, payload)
        if result is None:
            raise RuntimeError("LLM API 请求失败")

        try:
            content = result["choices"][0]["message"]["content"]
            return content.strip()
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError("解析 LLM 响应失败：" + str(e))

    def _safe_request(
        self, url: str, headers: dict, payload: dict
    ) -> Optional[dict]:
        """发送 HTTP POST 请求，带超时和重试。"""
        max_retries = 2
        timeout = 60

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url, headers=headers, json=payload, timeout=timeout
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(
                        "LLM API 频率限制，" + str(wait_time) + "秒后重试..."
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "LLM API 错误：status=" + str(response.status_code)
                        + ", body=" + response.text[:200]
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return None

            except requests.exceptions.Timeout:
                logger.warning(
                    "LLM API 请求超时（attempt "
                    + str(attempt + 1) + "/" + str(max_retries) + "）"
                )
                if attempt < max_retries - 1:
                    continue
                return None

            except requests.exceptions.RequestException as e:
                logger.error("LLM API 网络错误：" + str(e))
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None

        return None
