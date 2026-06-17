"""
TrendRadar - 命令行入口
用于非 Streamlit 场景下的测试和脚本调用。
"""

import sys
from dotenv import load_dotenv


def check_env():
    """检查环境变量配置状态，给出提示。"""
    import os
    github_token = os.getenv("GITHUB_TOKEN")
    llm_api_key = os.getenv("LLM_API_KEY")

    print("=== TrendRadar 环境检查 ===")
    if github_token:
        print("[OK] GITHUB_TOKEN 已配置")
    else:
        print("[提示] GITHUB_TOKEN 未配置，GitHub 数据将使用公开接口（有速率限制）")

    if llm_api_key:
        print("[OK] LLM_API_KEY 已配置")
    else:
        print("[提示] LLM_API_KEY 未配置，AI 报告将使用模板模式（仍然可用）")
    print("============================")


def main():
    """命令行主入口。"""
    load_dotenv()
    check_env()

    if len(sys.argv) < 2:
        print("用法:")
        print("  python main.py test      - 运行基础连通性测试")
        print("  streamlit run app.py     - 启动 Web 界面")
        return

    cmd = sys.argv[1]

    if cmd == "test":
        print("\n正在运行基础测试...")
        print()
        print("=" * 50)
        print("评分服务测试")
        print("=" * 50)
        from tests.test_scoring import run_basic_test
        run_basic_test()

        print()
        print("=" * 50)
        print("数据库测试")
        print("=" * 50)
        from tests.test_database import run_database_test
        run_database_test()

        print()
        print("=" * 50)
        print("AI 趋势报告 Agent 测试")
        print("=" * 50)
        from tests.test_agent import run_agent_test
        run_agent_test()

        print()
        print("所有测试完成。")
    else:
        print(f"未知命令：{cmd}")
        print("可用命令：test")


if __name__ == "__main__":
    main()
