"""
TrendRadar - Streamlit 前端入口
负责页面展示和用户交互，不包含业务逻辑。
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from collectors.github_collector import GitHubCollector
from collectors.hn_collector import HNCollector
from services.scoring_service import score_github_repos, score_hn_items
from services.report_service import ReportService
from database.db import init_db
from database.repository import (
    save_search, save_github_results, save_hn_results,
    get_recent_searches, save_report,
    get_search_by_id, get_github_results_by_search,
    get_hn_results_by_search, get_latest_report_by_search,
)


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _time_range_to_days(label: str) -> int:
    """将时间范围选项文字转换为天数。"""
    mapping = {"近7天": 7, "近14天": 14, "近30天": 30, "近90天": 90}
    return mapping.get(label, 30)


def _calc_heat_level(gh_avg: float, hn_avg: float) -> tuple:
    """根据 GitHub 和 Hacker News 平均分计算综合热度。返回 (文字, 颜色)。"""
    overall = (gh_avg + hn_avg) / 2
    if overall >= 70:
        return "非常活跃", "#2e7d32"
    elif overall >= 50:
        return "较活跃", "#1565c0"
    elif overall >= 30:
        return "一般", "#e65100"
    else:
        return "较低", "#616161"


# ------------------------------------------------------------------
# 样式注入
# ------------------------------------------------------------------

CUSTOM_CSS = """
<style>
.info-box {
    background: #f5f5f5;
    border-left: 4px solid #546e7a;
    padding: 0.8rem 1.2rem;
    border-radius: 0 4px 4px 0;
    margin-bottom: 0.5rem;
}
.info-box p {
    margin: 0.25rem 0;
    color: #37474f;
    font-size: 0.92rem;
    line-height: 1.5;
}
.metric-card {
    text-align: center;
    padding: 0.8rem 0.5rem;
    border-radius: 6px;
    background: #fafafa;
    border: 1px solid #e0e0e0;
}
.metric-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #1565c0;
    line-height: 1.2;
}
.metric-label {
    font-size: 0.8rem;
    color: #757575;
    margin-top: 0.2rem;
}
.section-note {
    padding: 0.5rem 0.8rem;
    background: #fafafa;
    border-left: 3px solid #90a4ae;
    color: #546e7a;
    font-size: 0.88rem;
    border-radius: 0 4px 4px 0;
    margin-top: 0.5rem;
}
</style>
"""


# ------------------------------------------------------------------
# 页面组件
# ------------------------------------------------------------------

def _render_info_box():
    """渲染页面顶部的轻量说明区。"""
    st.markdown(
        '<div class="info-box">'
        '<p>TrendRadar 用于采集 GitHub 和 Hacker News 公开数据，'
        '计算趋势评分，并生成面向求职和技术调研的分析报告。</p>'
        '<p><b>核心能力：</b>'
        '多源采集 | 趋势评分 | 历史记录 | AI 报告 | Markdown 导出</p>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_kpi_cards(gh_scored, hn_scored):
    """渲染分析概览指标卡（5 张 KPI 卡片）。"""
    gh_count = len(gh_scored) if gh_scored is not None and not gh_scored.empty else 0
    hn_count = len(hn_scored) if hn_scored is not None and not hn_scored.empty else 0

    if gh_count > 0 and "trend_score" in gh_scored.columns:
        gh_avg = round(float(gh_scored["trend_score"].mean()), 1)
    else:
        gh_avg = 0.0

    if hn_count > 0 and "trend_score" in hn_scored.columns:
        hn_avg = round(float(hn_scored["trend_score"].mean()), 1)
    else:
        hn_avg = 0.0

    heat_text, heat_color = _calc_heat_level(gh_avg, hn_avg)

    c1, c2, c3, c4, c5 = st.columns(5)
    cards = [
        (str(gh_count), "GitHub 结果数"),
        (str(hn_count), "Hacker News 讨论数"),
        (str(gh_avg), "GitHub 平均趋势分"),
        (str(hn_avg), "Hacker News 平均趋势分"),
    ]
    for col, (value, label) in zip([c1, c2, c3, c4], cards):
        col.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-value">{value}</div>'
            f'<div class="metric-label">{label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    c5.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-value" style="color:{heat_color};">{heat_text}</div>'
        f'<div class="metric-label">综合热度</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_sidebar():
    """渲染侧边栏：关键词输入、时间范围、分析按钮、历史搜索记录。"""
    history_clicked_id = None

    with st.sidebar:
        st.markdown("#### 分析设置")

        keyword = st.text_input(
            "技术关键词",
            placeholder="例如：AI Agent、LangGraph、FastAPI",
            key="keyword_input",
        )
        time_range = st.selectbox(
            "时间范围",
            options=["近7天", "近14天", "近30天", "近90天"],
            index=2,
            key="time_range",
        )

        analyze_clicked = st.button(
            "开始分析", type="primary", use_container_width=True
        )

        st.divider()

        # ---------- 历史搜索记录 ----------
        st.markdown("#### 历史搜索记录")

        limit_options = ["最近5条", "最近10条"]
        limit_choice = st.radio(
            "显示数量", limit_options, horizontal=True,
            index=0, key="history_limit_choice",
            label_visibility="collapsed",
        )
        history_limit = 10 if limit_choice == "最近10条" else 5

        try:
            history = get_recent_searches(limit=history_limit)
            if history:
                for i, item in enumerate(history):
                    st.markdown(
                        f"**{item['keyword']}**  \n"
                        f"范围：{item['days']}天 | "
                        f"GitHub {item['github_count']} | "
                        f"Hacker News {item['hn_count']}  \n"
                        f"时间：{item['created_at']}"
                    )
                    btn_key = f"hist_btn_{item['id']}"
                    if st.button("查看历史结果", key=btn_key,
                                 use_container_width=True):
                        history_clicked_id = item["id"]
                    if i < len(history) - 1:
                        st.divider()
            else:
                st.caption("暂无搜索记录")
        except Exception:
            st.caption("历史记录加载失败")

        st.divider()
        st.caption("TrendRadar v0.8.0")

    return keyword, time_range, analyze_clicked, history_clicked_id


# ------------------------------------------------------------------
# GitHub 分析区域
# ------------------------------------------------------------------

def _run_github_analysis(keyword: str, days: int):
    """
    调用 GitHub 采集器，展示结果表格和趋势评分 Top 10 柱状图。
    返回评分后的 DataFrame；失败时返回 None。
    """
    st.markdown("### GitHub 分析结果")

    with st.spinner(f"正在搜索 GitHub 上关于「{keyword}」的近期数据…"):
        try:
            collector = GitHubCollector()
            df = collector.collect_df(keyword, days=days, limit=20)
            meta = collector.last_result_meta
        except Exception as e:
            st.error(f"GitHub 采集过程中发生未知错误：{e}")
            return None

    # ---------- 空结果处理 ----------
    if df.empty:
        error_reason = meta.get("error_reason", "unknown")
        if error_reason == "api_rate_limited":
            st.warning(
                "GitHub API 请求频率超限，请稍后再试。\n\n"
                "解决方案：在项目根目录创建 `.env` 文件，"
                "填入 `GITHUB_TOKEN=你的个人访问令牌`，然后重启应用。"
                "配置 Token 后速率限制会大幅提升。"
            )
        elif error_reason == "network_error":
            st.warning(
                f"无法连接 GitHub API，请检查网络连接。\n\n"
                f"错误详情：{meta.get('error_message', '未知')}"
            )
        else:
            st.warning(
                f"未找到与「{keyword}」相关的 GitHub 仓库。\n\n"
                "可能原因：关键词过于小众或拼写有误、GitHub API 限流、或网络连接问题。"
            )
        return None

    # ---------- fallback 提示 ----------
    fallback_used = meta.get("fallback_used", False)
    query_level = meta.get("query_level", "strict")
    if fallback_used and query_level in ("fallback", "broad"):
        st.info(
            f"近 {days} 天内与「{keyword}」相关的活跃项目较少，"
            f"已自动扩大搜索范围（当前查询级别：{query_level}）。"
        )
    st.success(f"成功采集到 **{len(df)}** 条 GitHub 仓库数据。")

    # ---------- 评分 ----------
    try:
        scored_df = score_github_repos(df)
    except Exception as e:
        st.warning(f"趋势评分计算失败：{e}，已展示原始数据。")
        scored_df = df

    # ---------- 热门仓库表格 ----------
    st.markdown("**GitHub 热门仓库**")

    display_df = scored_df[
        ["repo_name", "owner", "stars", "forks", "language",
         "updated_at", "trend_score", "repo_url"]
    ].copy()
    display_df.columns = [
        "仓库名", "所有者", "Stars", "Forks", "主要语言",
        "最近更新日期", "趋势评分", "链接",
    ]
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df, use_container_width=True)

    # ---------- 趋势评分 Top 10 柱状图 ----------
    st.markdown("**GitHub 趋势评分 Top 10**")

    top10 = scored_df.head(10).copy()
    top10["label"] = top10["owner"] + "/" + top10["repo_name"]

    fig = px.bar(
        top10,
        x="label",
        y="trend_score",
        labels={"label": "仓库", "trend_score": "趋势评分"},
        color="trend_score",
        color_continuous_scale="blues",
    )
    fig.update_layout(
        xaxis_tickangle=-35,
        margin=dict(b=120),
        showlegend=False,
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---------- 评分说明 ----------
    st.markdown(
        '<div class="section-note">'
        '趋势评分综合 Stars、Forks、Issues 和时间新鲜度，'
        '不是简单按 Stars 排序。时间新鲜度模块让近期活跃的项目获得更高排名。'
        '</div>',
        unsafe_allow_html=True,
    )

    return scored_df


# ------------------------------------------------------------------
# Hacker News 分析区域
# ------------------------------------------------------------------

def _run_hn_analysis(keyword: str, days: int):
    """
    调用 Hacker News 采集器，展示热门讨论表格和趋势评分 Top 10 柱状图。
    返回评分后的 DataFrame；失败时返回 None。
    """
    st.markdown("### Hacker News 分析结果")

    with st.spinner(f"正在搜索 Hacker News 上关于「{keyword}」的讨论…"):
        try:
            collector = HNCollector()
            df = collector.collect_df(keyword, days=days, limit=20)
            meta = collector.last_result_meta
        except Exception as e:
            st.error(f"Hacker News 采集过程中发生未知错误：{e}")
            return None

    # ---------- 空结果处理 ----------
    if df.empty:
        error_reason = meta.get("error_reason", "unknown")
        if error_reason == "network_error":
            st.warning(
                f"无法连接 Hacker News API，请检查网络连接。\n\n"
                f"错误详情：{meta.get('error_message', '未知')}"
            )
        else:
            st.warning(
                f"未找到与「{keyword}」相关的 Hacker News 讨论，"
                f"可能是关键词过于小众或时间范围较短。"
            )
        return None

    # ---------- fallback 提示 ----------
    fallback_used = meta.get("fallback_used", False)
    query_level = meta.get("query_level", "strict")
    if fallback_used and query_level == "broad":
        st.info(
            f"近 {days} 天内相关讨论较少，已自动扩大搜索范围（全时段搜索）。"
        )
    st.success(f"成功采集到 **{len(df)}** 条 Hacker News 讨论。")

    # ---------- 评分 ----------
    try:
        scored_hn = score_hn_items(df)
    except Exception as e:
        st.warning(f"趋势评分计算失败：{e}，已展示原始数据。")
        scored_hn = df

    # ---------- 热门讨论表格 ----------
    st.markdown("**Hacker News 热门讨论**")

    display_df = scored_hn[
        ["title", "author", "points", "comments_count",
         "created_at", "trend_score", "url"]
    ].copy()
    display_df.columns = [
        "标题", "作者", "Points", "评论数",
        "创建时间", "趋势评分", "链接",
    ]
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df, use_container_width=True)

    # ---------- 趋势评分 Top 10 柱状图 ----------
    st.markdown("**Hacker News 趋势评分 Top 10**")

    top10 = scored_hn.head(10).copy()
    top10["short_title"] = top10["title"].apply(
        lambda t: t[:30] + "…" if len(t) > 30 else t
    )

    fig = px.bar(
        top10,
        x="short_title",
        y="trend_score",
        labels={"short_title": "帖子", "trend_score": "趋势评分"},
        color="trend_score",
        color_continuous_scale="oranges",
    )
    fig.update_layout(
        xaxis_tickangle=-35,
        margin=dict(b=120),
        showlegend=False,
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---------- 评分说明 ----------
    st.markdown(
        '<div class="section-note">'
        '趋势评分综合 Points、评论数和时间新鲜度，'
        '关注社区讨论热度和近期活跃度。'
        '</div>',
        unsafe_allow_html=True,
    )

    return scored_hn


# ------------------------------------------------------------------
# 数据库保存
# ------------------------------------------------------------------

def _save_to_database(keyword: str, days: int, gh_scored, hn_scored):
    """
    将搜索结果保存到 SQLite 数据库。
    所有异常均被捕获，不影响页面展示。

    Returns:
        search_id: 搜索记录 ID；失败时返回 None
    """
    try:
        gh_count = len(gh_scored) if gh_scored is not None and not gh_scored.empty else 0
        hn_count = len(hn_scored) if hn_scored is not None and not hn_scored.empty else 0

        search_id = save_search(keyword, days, gh_count, hn_count)
        if search_id is None:
            st.caption("搜索结果未能保存到数据库。")
            return None

        if gh_scored is not None and not gh_scored.empty:
            save_github_results(search_id, gh_scored)
        if hn_scored is not None and not hn_scored.empty:
            save_hn_results(search_id, hn_scored)

        st.caption(f"搜索结果已保存到数据库（ID: {search_id}）。")
        return search_id
    except Exception as e:
        st.caption(f"保存到数据库时发生错误：{e}")
        return None


# ------------------------------------------------------------------
# AI 报告区域
# ------------------------------------------------------------------

def _render_report_section():
    """渲染 AI 报告生成按钮和已生成的报告。"""
    st.markdown("### AI 趋势报告")

    st.caption(
        "无 API Key 时使用本地模板报告；"
        "配置 LLM_API_KEY 后可调用 OpenAI 兼容模型生成更深入分析。"
    )

    if st.button("生成 AI 趋势报告", use_container_width=True):
        st.session_state["_generate_report_flag"] = True
        st.rerun()

    # ---------- 展示已生成的报告 ----------
    if st.session_state.get("last_report_content"):
        mode = st.session_state.get("last_report_mode", "template")
        if mode == "llm":
            st.info("本报告由 AI 大模型生成，内容仅供参考。")
        else:
            st.info(
                "本报告基于规则模板生成。"
                "配置 LLM_API_KEY 后可获得 AI 深度分析报告。"
            )

        st.markdown(st.session_state["last_report_content"])

        filepath = st.session_state.get("last_report_filepath", "")
        if filepath:
            st.caption("报告已保存至：" + filepath)


def _generate_report():
    """
    调用 ReportService 生成 AI 趋势报告。
    从 session_state 读取上次分析结果，生成报告后保存 Markdown 文件和数据库记录。
    """
    keyword = st.session_state.get("last_keyword", "")
    days = st.session_state.get("last_days", 30)
    gh_scored = st.session_state.get("last_gh_scored")
    hn_scored = st.session_state.get("last_hn_scored")
    search_id = st.session_state.get("last_search_id")

    if not keyword:
        st.warning("没有可用的分析数据，请先执行搜索分析。")
        return

    # 构造分析数据字典
    analysis = {
        "github_df": gh_scored,
        "hn_df": hn_scored,
        "github_count": len(gh_scored) if gh_scored is not None and not gh_scored.empty else 0,
        "hn_count": len(hn_scored) if hn_scored is not None and not hn_scored.empty else 0,
        "days": days,
    }

    if gh_scored is not None and not gh_scored.empty and "trend_score" in gh_scored.columns:
        analysis["github_avg_score"] = round(float(gh_scored["trend_score"].mean()), 1)
    else:
        analysis["github_avg_score"] = 0

    if hn_scored is not None and not hn_scored.empty and "trend_score" in hn_scored.columns:
        analysis["hn_avg_score"] = round(float(hn_scored["trend_score"].mean()), 1)
    else:
        analysis["hn_avg_score"] = 0

    # 生成报告
    with st.spinner("正在生成 AI 趋势报告..."):
        try:
            service = ReportService()
            result = service.generate_and_save(keyword, analysis)
        except Exception as e:
            st.error(f"报告生成过程中发生错误：{e}")
            return

    if not result["success"]:
        st.error(f"报告生成失败：{result.get('error', '未知错误')}")
        return

    # 保存报告到 session_state
    st.session_state["last_report_content"] = result["content"]
    st.session_state["last_report_filepath"] = result["filepath"]
    st.session_state["last_report_mode"] = result["mode"]

    # 保存报告记录到数据库
    if search_id is not None:
        try:
            report_id = save_report(
                search_id=search_id,
                report_title=result["title"],
                report_content=result["content"],
                markdown_path=result["filepath"],
            )
            if report_id:
                st.success(f"报告已生成并保存（报告 ID: {report_id}）。")
            else:
                st.warning("报告已生成，但保存到数据库失败。")
        except Exception as e:
            st.warning(f"报告数据库保存失败：{e}")
    else:
        st.success("报告已生成。")

    st.rerun()


# ------------------------------------------------------------------
# 历史记录渲染（Phase 8.5）
# ------------------------------------------------------------------

def _render_history_results(search_id: int):
    """从数据库读取并渲染历史分析结果，不会重新请求 API。"""

    # 读取搜索记录
    search_record = get_search_by_id(search_id)
    if search_record is None:
        st.warning("未找到该历史记录。")
        return

    keyword = search_record["keyword"]
    days = search_record["days"]
    created_at = search_record["created_at"]

    st.info("当前展示的是历史记录，不会重新请求 GitHub 和 Hacker News API。")

    st.markdown(f"### 历史分析结果：{keyword}")
    st.caption(
        f"时间范围：近 {days} 天 | "
        f"搜索时间：{created_at} | "
        f"GitHub：{search_record['github_count']} 条 | "
        f"Hacker News：{search_record['hn_count']} 条"
    )

    # 读取 GitHub 和 HN 结果
    gh_df = get_github_results_by_search(search_id)
    hn_df = get_hn_results_by_search(search_id)

    # KPI 指标卡
    st.markdown("#### 本次分析概览")
    _render_kpi_cards(gh_df if not gh_df.empty else None,
                      hn_df if not hn_df.empty else None)

    # ---------- GitHub 结果 ----------
    if not gh_df.empty:
        st.markdown("### GitHub 分析结果")
        st.markdown("**GitHub 热门仓库**")

        display_gh = gh_df[
            ["ranking", "repo_name", "owner", "stars", "forks", "language",
             "updated_at", "trend_score", "repo_url"]
        ].copy()
        display_gh.columns = [
            "排名", "仓库名", "所有者", "Stars", "Forks", "主要语言",
            "最近更新日期", "趋势评分", "链接",
        ]
        st.dataframe(display_gh, use_container_width=True)

        if "trend_score" in gh_df.columns:
            st.markdown("**GitHub 趋势评分 Top 10**")
            top10 = gh_df.head(10).copy()
            top10["label"] = top10["owner"] + "/" + top10["repo_name"]
            fig = px.bar(
                top10, x="label", y="trend_score",
                labels={"label": "仓库", "trend_score": "趋势评分"},
                color="trend_score", color_continuous_scale="blues",
            )
            fig.update_layout(
                xaxis_tickangle=-35, margin=dict(b=120),
                showlegend=False, height=420,
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                '<div class="section-note">'
                '趋势评分综合 Stars、Forks、Issues 和时间新鲜度，'
                '不是简单按 Stars 排序。'
                '</div>',
                unsafe_allow_html=True,
            )

    # ---------- HN 结果 ----------
    if not hn_df.empty:
        st.markdown("### Hacker News 分析结果")
        st.markdown("**Hacker News 热门讨论**")

        display_hn = hn_df[
            ["ranking", "title", "author", "points", "comments_count",
             "created_at", "trend_score", "url"]
        ].copy()
        display_hn.columns = [
            "排名", "标题", "作者", "Points", "评论数",
            "创建时间", "趋势评分", "链接",
        ]
        st.dataframe(display_hn, use_container_width=True)

        if "trend_score" in hn_df.columns:
            st.markdown("**Hacker News 趋势评分 Top 10**")
            top10_hn = hn_df.head(10).copy()
            top10_hn["short_title"] = top10_hn["title"].apply(
                lambda t: t[:30] + "…" if len(t) > 30 else t
            )
            fig_hn = px.bar(
                top10_hn, x="short_title", y="trend_score",
                labels={"short_title": "帖子", "trend_score": "趋势评分"},
                color="trend_score", color_continuous_scale="oranges",
            )
            fig_hn.update_layout(
                xaxis_tickangle=-35, margin=dict(b=120),
                showlegend=False, height=420,
            )
            st.plotly_chart(fig_hn, use_container_width=True)

            st.markdown(
                '<div class="section-note">'
                '趋势评分综合 Points、评论数和时间新鲜度，'
                '关注社区讨论热度和近期活跃度。'
                '</div>',
                unsafe_allow_html=True,
            )

    # ---------- 报告 ----------
    st.markdown("### AI 趋势报告")
    report = get_latest_report_by_search(search_id)
    if report:
        st.markdown(report["report_content"])
        if report["markdown_path"]:
            st.caption("报告已保存至：" + report["markdown_path"])
    else:
        st.caption(
            "该历史记录暂未生成 AI 趋势报告，"
            "可重新分析后生成报告。"
        )


# ------------------------------------------------------------------
# 主页面
# ------------------------------------------------------------------

def render_main_page():
    """渲染主页面：标题、说明卡片、输入区域、分析结果与报告。"""

    # ===== 页面标题 =====
    st.title("TrendRadar：AI 技术趋势情报平台")
    st.markdown(
        "输入技术关键词（如 AI Agent、LangGraph、FastAPI），"
        "系统将分析该技术在 GitHub 和 Hacker News 上的近期趋势。"
    )

    # ===== 轻量说明区 =====
    _render_info_box()

    # ===== KPI 指标卡容器（预留位置，分析完成后填入） =====
    kpi_container = st.empty()

    # ===== 侧边栏（获取输入） =====
    keyword, time_range, analyze_clicked, history_clicked_id = _render_sidebar()

    # ===== 处理侧边栏按钮 =====

    # "开始分析" → 退出历史模式
    if analyze_clicked:
        st.session_state["history_mode"] = False
        st.session_state.pop("selected_history_id", None)

    # "查看历史结果" → 进入历史模式
    if history_clicked_id is not None:
        st.session_state["history_mode"] = True
        st.session_state["selected_history_id"] = history_clicked_id

    # ===== 历史模式渲染 =====
    if st.session_state.get("history_mode", False):
        search_id = st.session_state.get("selected_history_id")
        if search_id is not None:
            _render_history_results(search_id)

    # ===== 实时分析渲染 =====
    elif analyze_clicked:
        if not keyword.strip():
            st.warning("请输入至少一个技术关键词。")
        else:
            days = _time_range_to_days(time_range)
            kw = keyword.strip()

            # 清除上一份报告
            st.session_state.pop("last_report_content", None)
            st.session_state.pop("last_report_filepath", None)
            st.session_state.pop("last_report_mode", None)

            # 1. GitHub 分析（表格 + 柱状图 inline 渲染）
            gh_scored = _run_github_analysis(kw, days)

            # 2. Hacker News 分析（表格 + 柱状图 inline 渲染）
            hn_scored = _run_hn_analysis(kw, days)

            # 3. 保存到数据库
            search_id = _save_to_database(kw, days, gh_scored, hn_scored)

            # 4. 在顶部容器写入 KPI 指标卡
            kpi_container.markdown("#### 本次分析概览")
            _render_kpi_cards(gh_scored, hn_scored)
            kpi_container.markdown(
                f'<p style="color:#757575;font-size:0.85rem;">'
                f'关键词：{kw} &nbsp;|&nbsp; 时间范围：近 {days} 天</p>',
                unsafe_allow_html=True,
            )

            # 5. 存入 session_state
            st.session_state["last_keyword"] = kw
            st.session_state["last_days"] = days
            st.session_state["last_gh_scored"] = gh_scored
            st.session_state["last_hn_scored"] = hn_scored
            st.session_state["last_search_id"] = search_id

            # 6. AI 报告区域
            if gh_scored is not None or hn_scored is not None:
                st.divider()
                _render_report_section()

    # ===== 处理"生成报告"按钮（rerun 后执行） =====
    if st.session_state.get("_generate_report_flag", False):
        st.session_state["_generate_report_flag"] = False
        _generate_report()

    # ===== rerun 后渲染已有分析结果 =====
    # （仅在非"开始分析"点击 且 非历史模式时触发）
    if (
        not analyze_clicked
        and not st.session_state.get("history_mode", False)
        and (
            st.session_state.get("last_gh_scored") is not None
            or st.session_state.get("last_hn_scored") is not None
        )
    ):
        saved_gh = st.session_state.get("last_gh_scored")
        saved_hn = st.session_state.get("last_hn_scored")
        saved_kw = st.session_state.get("last_keyword", "")
        saved_days = st.session_state.get("last_days", 30)

        st.divider()

        # --- KPI 指标卡 ---
        st.markdown("#### 本次分析概览")
        _render_kpi_cards(saved_gh, saved_hn)
        st.caption(f"关键词：{saved_kw} | 时间范围：近 {saved_days} 天")

        # --- GitHub 详情 ---
        if saved_gh is not None and not saved_gh.empty:
            st.markdown("### GitHub 分析结果")
            st.markdown("**GitHub 热门仓库**")
            display_gh = saved_gh[
                ["repo_name", "owner", "stars", "forks", "language",
                 "updated_at", "trend_score", "repo_url"]
            ].copy()
            display_gh.columns = [
                "仓库名", "所有者", "Stars", "Forks", "主要语言",
                "最近更新日期", "趋势评分", "链接",
            ]
            display_gh.index = range(1, len(display_gh) + 1)
            st.dataframe(display_gh, use_container_width=True)

            if "trend_score" in saved_gh.columns:
                st.markdown("**GitHub 趋势评分 Top 10**")
                top10 = saved_gh.head(10).copy()
                top10["label"] = top10["owner"] + "/" + top10["repo_name"]
                fig = px.bar(
                    top10, x="label", y="trend_score",
                    labels={"label": "仓库", "trend_score": "趋势评分"},
                    color="trend_score", color_continuous_scale="blues",
                )
                fig.update_layout(
                    xaxis_tickangle=-35, margin=dict(b=120),
                    showlegend=False, height=420,
                )
                st.plotly_chart(fig, use_container_width=True)

                st.markdown(
                    '<div class="section-note">'
                    '趋势评分综合 Stars、Forks、Issues 和时间新鲜度，'
                    '不是简单按 Stars 排序。'
                    '</div>',
                    unsafe_allow_html=True,
                )

        # --- HN 详情 ---
        if saved_hn is not None and not saved_hn.empty:
            st.markdown("### Hacker News 分析结果")
            st.markdown("**Hacker News 热门讨论**")
            display_hn = saved_hn[
                ["title", "author", "points", "comments_count",
                 "created_at", "trend_score", "url"]
            ].copy()
            display_hn.columns = [
                "标题", "作者", "Points", "评论数",
                "创建时间", "趋势评分", "链接",
            ]
            display_hn.index = range(1, len(display_hn) + 1)
            st.dataframe(display_hn, use_container_width=True)

            if "trend_score" in saved_hn.columns:
                st.markdown("**Hacker News 趋势评分 Top 10**")
                top10_hn = saved_hn.head(10).copy()
                top10_hn["short_title"] = top10_hn["title"].apply(
                    lambda t: t[:30] + "…" if len(t) > 30 else t
                )
                fig_hn = px.bar(
                    top10_hn, x="short_title", y="trend_score",
                    labels={"short_title": "帖子", "trend_score": "趋势评分"},
                    color="trend_score", color_continuous_scale="oranges",
                )
                fig_hn.update_layout(
                    xaxis_tickangle=-35, margin=dict(b=120),
                    showlegend=False, height=420,
                )
                st.plotly_chart(fig_hn, use_container_width=True)

                st.markdown(
                    '<div class="section-note">'
                    '趋势评分综合 Points、评论数和时间新鲜度，'
                    '关注社区讨论热度和近期活跃度。'
                    '</div>',
                    unsafe_allow_html=True,
                )

        # --- AI 报告区域 ---
        _render_report_section()

    # ===== 页面底部 =====
    st.divider()
    with st.expander("TrendRadar 能帮你做什么？"):
        st.markdown(
            "- **求职选题**：发现当前热门技术方向，为简历项目选题提供参考。\n"
            "- **技术调研**：快速了解某项技术的社区活跃度与增长趋势。\n"
            "- **学习规划**：判断某项技术是否值得投入时间学习。"
        )


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main():
    """Streamlit 应用主入口。"""
    init_db()

    st.set_page_config(
        page_title="TrendRadar",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    render_main_page()


if __name__ == "__main__":
    main()
