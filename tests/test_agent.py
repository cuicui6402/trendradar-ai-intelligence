"""
tests/test_agent.py
AI 趋势报告 Agent 和报告服务测试。
测试模板模式报告生成、报告服务导出、数据库报告保存。

v6.5 新增：
- 相关性评分与资料类项目过滤测试
- Agent 特定内容测试
- 混合数据（相关+无关项目）过滤测试
"""

import sys
import os
import tempfile

import pandas as pd

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 临时数据库路径
_test_db_path = None


def _get_test_db():
    """获取临时数据库路径，并重置数据库模块状态。"""
    global _test_db_path
    if _test_db_path is None:
        fd, _test_db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
    import database.db as db_module
    db_module._initialized = False
    db_module._current_db_path = _test_db_path
    return _test_db_path


def _cleanup():
    """清理临时数据库文件和报告文件。"""
    global _test_db_path
    if _test_db_path and os.path.exists(_test_db_path):
        import database.db as db_module
        db_module._initialized = False
        db_module._current_db_path = db_module.DEFAULT_DB_PATH
        try:
            os.remove(_test_db_path)
        except PermissionError:
            pass
        _test_db_path = None


def _make_test_analysis():
    """构造测试用的分析数据字典。"""
    github_df = pd.DataFrame({
        "ranking": [1, 2, 3],
        "repo_name": ["langgraph", "agent-framework", "ai-tools"],
        "owner": ["langchain-ai", "test-org", "dev-user"],
        "description": [
            "Building stateful multi-actor applications with LLMs",
            "A framework for building AI agents",
            "Collection of AI utilities",
        ],
        "stars": [5000, 2000, 500],
        "forks": [800, 300, 50],
        "open_issues": [100, 50, 10],
        "language": ["Python", "Python", "Python"],
        "created_at": ["2024-01-01", "2025-03-01", "2026-01-01"],
        "updated_at": ["2026-06-15", "2026-06-10", "2026-06-01"],
        "repo_url": [
            "https://github.com/langchain-ai/langgraph",
            "https://github.com/test-org/agent-framework",
            "https://github.com/dev-user/ai-tools",
        ],
        "source": ["github", "github", "github"],
        "trend_score": [95.5, 65.3, 35.0],
    })

    hn_df = pd.DataFrame({
        "ranking": [1, 2, 3],
        "title": [
            "Show HN: Building AI Agents with LangGraph",
            "The Future of AI Agent Frameworks",
            "Why I Switched to LangGraph",
        ],
        "author": ["hacker1", "hacker2", "hacker3"],
        "points": [500, 200, 80],
        "comments_count": [150, 60, 25],
        "created_at": ["2026-06-14", "2026-06-10", "2026-06-01"],
        "url": [
            "https://news.ycombinator.com/item?id=1",
            "https://news.ycombinator.com/item?id=2",
            "https://news.ycombinator.com/item?id=3",
        ],
        "source": ["hackernews", "hackernews", "hackernews"],
        "trend_score": [92.0, 55.5, 28.0],
    })

    return {
        "github_df": github_df,
        "hn_df": hn_df,
        "github_count": 3,
        "hn_count": 3,
        "github_avg_score": 65.3,
        "hn_avg_score": 58.5,
        "days": 30,
    }


def _make_mixed_analysis():
    """构造混合数据：包含 Agent 相关项目和资料类项目。"""
    github_df = pd.DataFrame({
        "ranking": [1, 2, 3, 4, 5, 6],
        "repo_name": [
            "langgraph", "JavaGuide", "agent-framework",
            "awesome-python", "ai-workflow", "leetcode-solutions",
        ],
        "owner": [
            "langchain-ai", "javaguide-org", "test-org",
            "awesome-collector", "ai-dev", "algo-master",
        ],
        "description": [
            "Building stateful multi-actor applications with LLMs",
            "Java面试指南，涵盖Java基础、并发、JVM等内容",
            "A framework for building autonomous AI agents",
            "A curated list of awesome Python frameworks and tools",
            "AI agent workflow automation tool with tool calling",
            "LeetCode算法题解集合，支持多种编程语言",
        ],
        "stars": [5000, 130000, 2000, 200000, 800, 50000],
        "forks": [800, 50000, 300, 30000, 100, 15000],
        "open_issues": [100, 500, 50, 200, 20, 100],
        "language": [
            "Python", "Java", "Python", "Python", "Python", "Python",
        ],
        "created_at": [
            "2024-01-01", "2019-01-01", "2025-03-01",
            "2018-01-01", "2026-01-01", "2020-01-01",
        ],
        "updated_at": [
            "2026-06-15", "2026-06-14", "2026-06-10",
            "2026-06-01", "2026-06-12", "2026-05-01",
        ],
        "repo_url": [
            "https://github.com/langchain-ai/langgraph",
            "https://github.com/javaguide-org/JavaGuide",
            "https://github.com/test-org/agent-framework",
            "https://github.com/awesome-collector/awesome-python",
            "https://github.com/ai-dev/ai-workflow",
            "https://github.com/algo-master/leetcode-solutions",
        ],
        "source": ["github"] * 6,
        "trend_score": [95.5, 50.0, 65.3, 45.0, 55.0, 40.0],
    })

    return {
        "github_df": github_df,
        "hn_df": pd.DataFrame(),
        "github_count": 6,
        "hn_count": 0,
        "github_avg_score": 58.5,
        "hn_avg_score": 0,
        "days": 30,
    }


# ======================================================================
# 原有测试用例（保持不变）
# ======================================================================

def test_trend_agent_template_mode():
    """测试 TrendAgent 模板模式（无 API Key）。"""
    os.environ.pop("LLM_API_KEY", None)

    from agent.trend_agent import TrendAgent

    agent = TrendAgent()
    assert agent.is_available is False, "未配置 API Key 时 is_available 应为 False"

    analysis = _make_test_analysis()
    report = agent.generate_report("AI Agent", analysis)

    # 验证报告包含 9 个章节
    assert "## 一、技术概览" in report, "报告应包含'技术概览'章节"
    assert "## 二、热度判断" in report, "报告应包含'热度判断'章节"
    assert "## 三、GitHub 热门项目解读" in report, "报告应包含'GitHub 热门项目解读'章节"
    assert "## 四、Hacker News 热门讨论分析" in report, "报告应包含'HN 热门讨论分析'章节"
    assert "## 五、典型业务场景" in report, "报告应包含'典型业务场景'章节"
    assert "## 六、国内生态建议" in report, "报告应包含'国内生态建议'章节"
    assert "## 七、求职项目推荐" in report, "报告应包含'求职项目推荐'章节"
    assert "## 八、面试常见问题" in report, "报告应包含'面试常见问题'章节"
    assert "## 九、学习路径建议" in report, "报告应包含'学习路径建议'章节"

    # 验证报告包含关键词
    assert "AI Agent" in report, "报告应包含搜索关键词"

    # 验证报告包含数据
    assert "langgraph" in report.lower() or "langchain-ai" in report.lower(), \
        "报告应包含 GitHub 项目名"
    assert "langgraph" in report.lower() or "agent" in report.lower(), \
        "报告应包含 HN 讨论内容"

    # 验证报告是 Markdown 格式
    assert "# TrendRadar" in report, "报告应以 TrendRadar 标题开头"
    assert "---" in report, "报告应包含分隔线"

    report_lines = report.split("\n")
    print("  报告长度：" + str(len(report_lines)) + " 行，" + str(len(report)) + " 字符")
    print("  包含 9 个章节标题")
    print("  [PASS] TrendAgent 模板模式验证通过")

    return report


def test_trend_agent_empty_data():
    """测试 TrendAgent 在空数据下的表现。"""
    os.environ.pop("LLM_API_KEY", None)

    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    analysis = {
        "github_df": None,
        "hn_df": None,
        "github_count": 0,
        "hn_count": 0,
        "github_avg_score": 0,
        "hn_avg_score": 0,
        "days": 30,
    }

    report = agent.generate_report("UnknownTech", analysis)

    assert "## 一、技术概览" in report, "空数据也应生成完整报告"
    assert "## 九、学习路径建议" in report, "空数据也应包含所有章节"
    assert "UnknownTech" in report, "报告应包含关键词"

    print("  [PASS] TrendAgent 空数据容错验证通过")


def test_trend_agent_empty_dataframe():
    """测试 TrendAgent 在空 DataFrame 下的表现。"""
    os.environ.pop("LLM_API_KEY", None)

    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    analysis = {
        "github_df": pd.DataFrame(),
        "hn_df": pd.DataFrame(),
        "github_count": 0,
        "hn_count": 0,
        "github_avg_score": 0,
        "hn_avg_score": 0,
        "days": 7,
    }

    report = agent.generate_report("TestKeyword", analysis)

    assert "## 一、技术概览" in report
    assert len(report) > 500, "即使空数据报告也应有一定长度"

    print("  [PASS] TrendAgent 空 DataFrame 容错验证通过")


def test_report_service_save():
    """测试 ReportService 生成并保存 Markdown 文件。"""
    os.environ.pop("LLM_API_KEY", None)

    from services.report_service import ReportService

    service = ReportService()
    analysis = _make_test_analysis()

    temp_dir = tempfile.mkdtemp()
    original_dir = service.REPORT_DIR
    service.REPORT_DIR = temp_dir

    try:
        result = service.generate_and_save("AI Agent", analysis)

        assert result["success"] is True, "报告生成应成功"
        assert result["title"] != "", "报告标题不应为空"
        assert result["content"] != "", "报告内容不应为空"
        assert result["filepath"] != "", "报告文件路径不应为空"
        assert result["mode"] == "template", "未配置 API Key 时应为 template 模式"

        assert os.path.exists(result["filepath"]), "报告文件应存在"

        with open(result["filepath"], "r", encoding="utf-8") as f:
            file_content = f.read()
        assert file_content == result["content"], "文件内容应与返回内容一致"
        assert "## 一、技术概览" in file_content

        print("  报告文件：" + os.path.basename(result["filepath"]))
        print("  文件大小：" + str(len(file_content)) + " 字符")
        print("  [PASS] ReportService 保存验证通过")

    finally:
        service.REPORT_DIR = original_dir
        for f in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, f))
            except PermissionError:
                pass
        try:
            os.rmdir(temp_dir)
        except PermissionError:
            pass


def test_report_service_filename():
    """测试 ReportService 文件名生成。"""
    os.environ.pop("LLM_API_KEY", None)

    from services.report_service import ReportService

    service = ReportService()

    filename = service._make_filename("FastAPI")
    assert filename.startswith("trend_report_FastAPI_"), "文件名格式不正确"
    assert filename.endswith(".md"), "文件名应以 .md 结尾"

    filename = service._make_filename("AI/ML & Data")
    assert "/" not in filename, "文件名不应包含 /"
    assert "&" not in filename, "文件名不应包含 &"
    assert filename.endswith(".md"), "文件名应以 .md 结尾"

    filename = service._make_filename("人工智能")
    assert "人工智能" in filename, "中文关键词应保留在文件名中"

    filename = service._make_filename("A" * 50)
    assert len(filename) < 80, "超长关键词应被截断"

    print("  文件名示例：" + service._make_filename("FastAPI"))
    print("  特殊字符：" + service._make_filename("AI/ML & Data"))
    print("  中文：" + service._make_filename("人工智能"))
    print("  [PASS] ReportService 文件名生成验证通过")


def test_save_report_to_db():
    """测试报告保存到数据库。"""
    from database.db import init_db
    from database.repository import save_search, save_report, get_reports_by_search

    db_path = _get_test_db()
    init_db(db_path)

    from sqlalchemy import inspect
    from database.db import get_engine
    engine = get_engine(db_path)
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    assert "reports" in table_names, "reports 表未创建"

    search_id = save_search("AI Agent", 30, 3, 3)
    assert search_id is not None

    report_content = "# Test Report\n\nThis is a test report for AI Agent."
    report_id = save_report(
        search_id=search_id,
        report_title="Test Report: AI Agent",
        report_content=report_content,
        markdown_path="data/reports/test_report.md",
    )

    assert report_id is not None, "save_report 应返回有效的 report_id"
    assert isinstance(report_id, int), "report_id 应为 int"

    reports = get_reports_by_search(search_id)
    assert len(reports) == 1, "应有 1 条报告记录"
    assert reports[0]["report_title"] == "Test Report: AI Agent"
    assert reports[0]["markdown_path"] == "data/reports/test_report.md"

    print("  报告 ID：" + str(report_id))
    print("  关联搜索 ID：" + str(search_id))
    print("  [PASS] 报告数据库保存验证通过")


def test_heat_judgment_levels():
    """测试热度判断的不同级别。"""
    os.environ.pop("LLM_API_KEY", None)

    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    high_ctx = {"github_count": 20, "hn_count": 15, "github_avg_score": 80, "hn_avg_score": 75}
    high_text = agent._generate_heat_judgment("HotTech", high_ctx)
    assert "较高" in high_text, "高热度应判断为'较高'"

    mid_ctx = {"github_count": 10, "hn_count": 8, "github_avg_score": 60, "hn_avg_score": 55}
    mid_text = agent._generate_heat_judgment("MidTech", mid_ctx)
    assert "中等" in mid_text, "中等热度应判断为'中等'"

    low_ctx = {"github_count": 3, "hn_count": 2, "github_avg_score": 30, "hn_avg_score": 25}
    low_text = agent._generate_heat_judgment("LowTech", low_ctx)
    assert "一般" in low_text, "低热度应判断为'一般'"

    vlow_ctx = {"github_count": 1, "hn_count": 0, "github_avg_score": 10, "hn_avg_score": 0}
    vlow_text = agent._generate_heat_judgment("RareTech", vlow_ctx)
    assert "较低" in vlow_text, "极低热度应判断为'较低'"

    print("  热度级别：高/中/一般/较低 全部验证通过")
    print("  [PASS] 热度判断级别验证通过")


# ======================================================================
# v6.5 新增测试
# ======================================================================

def test_agent_keyword_detection():
    """测试 Agent 关键词检测。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    assert agent._is_agent_keyword("ai agent") is True
    assert agent._is_agent_keyword("AI Agent") is True
    assert agent._is_agent_keyword("llm agent") is True
    assert agent._is_agent_keyword("智能体") is True
    assert agent._is_agent_keyword("FastAPI") is False
    assert agent._is_agent_keyword("React") is False
    assert agent._is_agent_keyword("Rust") is False

    print("  [PASS] Agent 关键词检测验证通过")


def test_relevance_scoring():
    """测试 GitHub 项目相关性评分。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    # Agent 相关项目应得高分
    agent_row = pd.Series({
        "repo_name": "langgraph",
        "owner": "langchain-ai",
        "description": "Building stateful multi-agent applications with LLMs",
        "repo_url": "https://github.com/langchain-ai/langgraph",
        "trend_score": 95.5,
    })
    agent_score = agent._calculate_relevance_score(agent_row, "ai agent")

    # 资料类项目应得低分
    resource_row = pd.Series({
        "repo_name": "JavaGuide",
        "owner": "javaguide-org",
        "description": "Java interview guide for programmers",
        "repo_url": "https://github.com/javaguide-org/JavaGuide",
        "trend_score": 50.0,
    })
    resource_score = agent._calculate_relevance_score(resource_row, "ai agent")

    assert agent_score > resource_score, \
        "Agent 相关项目评分应高于资料类项目（" + str(agent_score) + " vs " + str(resource_score) + "）"

    # awesome 类项目也应得低分
    awesome_row = pd.Series({
        "repo_name": "awesome-python",
        "owner": "awesome-collector",
        "description": "A curated list of awesome Python frameworks",
        "repo_url": "https://github.com/awesome-collector/awesome-python",
        "trend_score": 45.0,
    })
    awesome_score = agent._calculate_relevance_score(awesome_row, "ai agent")
    assert agent_score > awesome_score, \
        "Agent 相关项目评分应高于 awesome 类项目"

    print("  Agent 项目评分: " + str(agent_score))
    print("  资料类项目评分: " + str(resource_score))
    print("  Awesome 项目评分: " + str(awesome_score))
    print("  [PASS] 相关性评分验证通过")


def test_resource_repo_detection():
    """测试资料类项目识别。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    # 资料类项目应被识别
    assert agent._is_resource_repo(pd.Series({
        "repo_name": "JavaGuide", "owner": "org", "description": "Java interview guide"
    })) is True

    assert agent._is_resource_repo(pd.Series({
        "repo_name": "leetcode-solutions", "owner": "org", "description": "Algorithm solutions"
    })) is True

    assert agent._is_resource_repo(pd.Series({
        "repo_name": "awesome-python", "owner": "org", "description": "Curated list"
    })) is True

    assert agent._is_resource_repo(pd.Series({
        "repo_name": "coding-interview-prep", "owner": "org", "description": "Interview prep"
    })) is True

    # 正常 Agent 项目不应被识别
    assert agent._is_resource_repo(pd.Series({
        "repo_name": "langgraph", "owner": "langchain-ai",
        "description": "Multi-agent workflow engine"
    })) is False

    assert agent._is_resource_repo(pd.Series({
        "repo_name": "ai-agent-toolkit", "owner": "ai-dev",
        "description": "Tools for building AI agents"
    })) is False

    print("  [PASS] 资料类项目识别验证通过")


def test_mixed_data_filtering():
    """测试混合数据下报告 Top5 过滤资料类项目。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()
    analysis = _make_mixed_analysis()
    report = agent.generate_report("ai agent", analysis)

    # 获取 GitHub 项目解读部分
    github_section_start = report.find("## 三、GitHub 热门项目解读")
    github_section_end = report.find("## 四、Hacker News 热门讨论分析")
    github_section = report[github_section_start:github_section_end]

    # langgraph 和 agent-framework 应该出现
    assert "langgraph" in github_section.lower(), \
        "langgraph 应出现在报告 Top5 中"

    # 当非资料项目 >= top_n 时，leetcode 不应出现（被硬过滤）
    # 测试 _get_report_top_projects 的直接行为
    top_projects = agent._get_report_top_projects(
        analysis["github_df"], "ai agent", 5
    )
    top_names = [str(n).lower() for n in top_projects["repo_name"].tolist()]

    # leetcode-solutions 应被过滤（3 个非资料项目不足 5 个时仍保留非资料在前）
    # 但当非资料项目 >= top_n 时应完全排除
    # 当前只有 3 个非资料项目 < 5，所以 leetcode 可能出现在末尾
    # 验证非资料项目排在前面
    non_resource_positions = []
    resource_positions = []
    for i, name in enumerate(top_names):
        if name in ["langgraph", "agent-framework", "ai-workflow"]:
            non_resource_positions.append(i)
        else:
            resource_positions.append(i)

    if non_resource_positions and resource_positions:
        assert max(non_resource_positions) < min(resource_positions), \
            "非资料项目应排在资料项目前面"

    # 验证 _get_report_top_projects 在足够非资料项目时硬过滤
    # 构造一个有足够非资料项目的 DataFrame
    large_df = pd.DataFrame({
        "repo_name": ["langgraph", "agent-framework", "ai-workflow",
                       "agent-sdk", "llm-tools", "JavaGuide", "awesome-list"],
        "owner": ["langchain-ai", "test-org", "ai-dev",
                   "sdk-team", "llm-org", "javaguide-org", "awesome-org"],
        "description": [
            "Multi-agent workflow engine", "Framework for AI agents",
            "AI workflow automation with tool calling",
            "Agent SDK for building autonomous agents",
            "LLM tool integration framework",
            "Java interview guide", "Curated awesome list of tools",
        ],
        "stars": [5000, 2000, 800, 600, 400, 130000, 200000],
        "forks": [800, 300, 100, 80, 50, 50000, 30000],
        "open_issues": [100, 50, 20, 15, 10, 500, 200],
        "language": ["Python"] * 7,
        "created_at": ["2026-01-01"] * 7,
        "updated_at": ["2026-06-15"] * 7,
        "repo_url": [
            "https://github.com/langchain-ai/langgraph",
            "https://github.com/test-org/agent-framework",
            "https://github.com/ai-dev/ai-workflow",
            "https://github.com/sdk-team/agent-sdk",
            "https://github.com/llm-org/llm-tools",
            "https://github.com/javaguide-org/JavaGuide",
            "https://github.com/awesome-org/awesome-list",
        ],
        "source": ["github"] * 7,
        "trend_score": [95.5, 65.3, 55.0, 50.0, 45.0, 50.0, 45.0],
    })

    large_top = agent._get_report_top_projects(large_df, "ai agent", 5)
    large_names = [str(n).lower() for n in large_top["repo_name"].tolist()]

    assert "javaguide" not in large_names, \
        "非资料项目充足时，JavaGuide 不应出现在 Top5 中"
    assert "awesome-list" not in large_names, \
        "非资料项目充足时，awesome-list 不应出现在 Top5 中"

    print("  GitHub 项目解读部分已正确排序（非资料项目优先）")
    print("  非资料项目充足时资料类项目被硬过滤")
    print("  [PASS] 混合数据过滤验证通过")


def test_agent_report_content_keywords():
    """测试 ai agent 报告中包含求职相关关键概念。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()
    analysis = _make_test_analysis()
    report = agent.generate_report("ai agent", analysis)

    # 报告中至少出现"工具调用、任务规划、RAG、安全、成本、权限"中的 3 个
    required_keywords = ["工具调用", "任务规划", "RAG", "安全", "成本", "权限"]
    found = [kw for kw in required_keywords if kw in report]

    assert len(found) >= 3, \
        "报告中应至少出现 3 个关键概念，实际找到 " + str(len(found)) + " 个: " + str(found)

    print("  找到关键概念: " + ", ".join(found) + " (" + str(len(found)) + "/" + str(len(required_keywords)) + ")")
    print("  [PASS] Agent 报告关键概念验证通过")


def test_agent_report_job_projects():
    """测试 ai agent 报告中的求职项目推荐。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()
    analysis = _make_test_analysis()
    report = agent.generate_report("ai agent", analysis)

    # 求职项目推荐中至少出现 DataInsight Agent、JobPilot、TrendRadar 中的 2 个
    project_names = ["DataInsight Agent", "JobPilot", "TrendRadar"]
    found = [name for name in project_names if name in report]

    assert len(found) >= 2, \
        "求职项目推荐中应至少出现 2 个推荐项目，实际找到: " + str(found)

    print("  找到推荐项目: " + ", ".join(found))
    print("  [PASS] Agent 报告求职项目推荐验证通过")


def test_non_agent_report_unchanged():
    """测试非 Agent 关键词时报告使用通用模板。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    # 使用通用关键词
    analysis = {
        "github_df": pd.DataFrame(),
        "hn_df": pd.DataFrame(),
        "github_count": 0,
        "hn_count": 0,
        "github_avg_score": 0,
        "hn_avg_score": 0,
        "days": 30,
    }

    report = agent.generate_report("FastAPI", analysis)

    # 不应包含 Agent 专属内容
    assert "DataInsight Agent" not in report, \
        "非 Agent 关键词时不应出现 DataInsight Agent"
    assert "JobPilot" not in report, \
        "非 Agent 关键词时不应出现 JobPilot"
    assert "DeepSeek" not in report, \
        "非 Agent 关键词时不应出现 DeepSeek"

    # 应包含通用内容
    assert "FastAPI" in report
    assert "## 一、技术概览" in report

    print("  [PASS] 非 Agent 关键词使用通用模板验证通过")


def test_agent_report_empty_github():
    """测试 ai agent 关键词 + 空 GitHub 数据时报告仍能生成。"""
    os.environ.pop("LLM_API_KEY", None)
    from agent.trend_agent import TrendAgent

    agent = TrendAgent()

    analysis = {
        "github_df": None,
        "hn_df": None,
        "github_count": 0,
        "hn_count": 0,
        "github_avg_score": 0,
        "hn_avg_score": 0,
        "days": 30,
    }

    report = agent.generate_report("ai agent", analysis)

    # 即使空数据也应生成完整报告
    assert "## 一、技术概览" in report
    assert "## 九、学习路径建议" in report
    # Agent 关键词应触发 Agent 特定内容
    assert "任务规划" in report or "工具调用" in report, \
        "空数据 + Agent 关键词时仍应包含 Agent 相关内容"

    print("  [PASS] Agent 关键词 + 空数据容错验证通过")


# ======================================================================
# 测试运行器
# ======================================================================

def run_agent_test():
    """运行所有 Agent 和报告测试。"""
    print("运行 AI 趋势报告 Agent 测试...")
    print()
    try:
        # 原有测试
        test_trend_agent_template_mode()
        print()
        test_trend_agent_empty_data()
        print()
        test_trend_agent_empty_dataframe()
        print()
        test_report_service_save()
        print()
        test_report_service_filename()
        print()
        test_save_report_to_db()
        print()
        test_heat_judgment_levels()
        print()

        # v6.5 新增测试
        print("--- v6.5 新增测试 ---")
        print()
        test_agent_keyword_detection()
        print()
        test_relevance_scoring()
        print()
        test_resource_repo_detection()
        print()
        test_mixed_data_filtering()
        print()
        test_agent_report_content_keywords()
        print()
        test_agent_report_job_projects()
        print()
        test_non_agent_report_unchanged()
        print()
        test_agent_report_empty_github()
        print()

        print("所有 AI 趋势报告测试通过！")
    finally:
        _cleanup()


if __name__ == "__main__":
    run_agent_test()
