#!/usr/bin/env python3
"""
MiniClaude — 从零构建的 AI Coding Agent。

入口文件：启动 REPL 交互循环。
"""

from pathlib import Path

from core.llm_client import LLMClient
from core.agent_loop import agent_loop
from core.toolbox import registry, todo_mgr, task_mgr, bg_mgr, skill_loader, set_registry_client, team_mgr, team_bus
from context import CompactManager

WORKDIR = Path.cwd()

# CompactManager 在 agent_loop 中通过 set_client() 延迟注入 _client
compact_mgr = CompactManager(WORKDIR)

# Layer 1: 技能名称+描述注入 system prompt
SYSTEM = f"""你是一个在 {WORKDIR} 工作的编程助手（Team Lead）。
使用 TodoWrite 跟踪多步骤任务，使用 task_create/task_update/task_list 管理持久化任务，
使用 background_run 执行耗时命令，使用 task 派生子代理探索或执行独立子任务。
使用 spawn_teammate 启动队友并行工作，通过 send_message/read_inbox/broadcast 与队友通信。
当对话过长时使用 compact 压缩上下文。遇到陌生领域时，先调用 load_skill 加载知识再行动。

可用技能:
{skill_loader.get_descriptions()}"""


def main():
    print(f"\033[36mMiniClaude 启动 — 工作区: {WORKDIR}\033[0m")
    print("输入 q / exit / 空行 退出")
    print("命令: /tasks 查看任务  /skills 查看技能  /team 查看队友  /compact 手动压缩\n")

    client = LLMClient()
    print(f"模型: {client.model}")

    # 将 client 注入给 task 工具和 team 模块使用
    set_registry_client(client)
    team_mgr.set_client(client)

    history = []
    while True:
        try:
            query = input("\033[36m>> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if query.strip().lower() in ("q", "exit", ""):
            break

        # 内置命令
        if query.strip() == "/tasks":
            print(task_mgr.list_all())
            continue
        if query.strip() == "/skills":
            print("可用技能:")
            print(skill_loader.get_descriptions())
            continue
        if query.strip() == "/team":
            print(team_mgr.list_all())
            continue
        if query.strip() == "/compact":
            if history:
                print("[手动压缩 /compact]")
                compacted = compact_mgr.compact(history)
                if compacted is not None:
                    history[:] = compacted
            continue

        history.append({"role": "user", "content": query})
        agent_loop(
            history, system=SYSTEM, client=client,
            tools_registry=registry,
            todo_manager=todo_mgr,
            bg_manager=bg_mgr,
            compact_manager=compact_mgr,
            team_bus=team_bus,
        )

        # 打印最后一条 assistant 回复中的文本
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()


if __name__ == "__main__":
    main()
