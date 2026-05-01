"""
核心 Agent Loop。

每轮处理流程:
    ┌─────────────────────────────────────────────┐
    │ 1. micro_compact  — 静默清理旧工具结果      │
    │ 2. auto_compact?  — 超过阈值则 LLM 摘要     │
    │ 3. drain bg notifs— 后台任务完成通知注入     │
    │ 4. LLM call       — 模型决策                │
    │ 5. execute tools  — 分发执行                 │
    │ 6. todo nag       — 3 轮未更新则提醒         │
    │ 7. manual compact?— 模型主动触发压缩         │
    └─────────────────────────────────────────────┘
"""
import json

from core.llm_client import LLMClient
from core.toolbox import registry
from managers import TodoManager, BackgroundManager
from context import CompactManager


def agent_loop(
    messages: list[dict],
    system: str = "",
    client: LLMClient = None,
    tools_registry=None,
    todo_manager: TodoManager = None,
    bg_manager: BackgroundManager = None,
    compact_manager: CompactManager = None,
    team_bus=None,  # MessageBus, 用于 drain lead inbox
):
    if client is None:
        client = LLMClient()
    if tools_registry is None:
        tools_registry = registry

    # 延迟注入: CompactManager 需要 LLMClient 来做摘要调用
    if compact_manager is not None:
        compact_manager.set_client(client)

    schemas = tools_registry.get_schemas()
    rounds_since_todo = 0

    while True:
        # ── Layer 1: micro_compact — 每轮静默替换旧工具结果 ──
        if compact_manager is not None:
            compact_manager.micro_compact(messages)

        # ── Layer 2: auto_compact — 超阈值自动摘要 ────────────
        if compact_manager is not None and compact_manager.should_compact(messages):
            print("[auto_compact triggered]")
            compacted = compact_manager.compact(messages)
            if compacted is not None:
                messages[:] = compacted
                # 压缩后继续循环——LLM 基于摘要重新决策
                continue

        # ── 后台任务通知注入 ──────────────────────────────────
        if bg_manager is not None:
            notifs = bg_manager.drain_notifications()
            if notifs:
                text = "\n".join(
                    f"[bg:{n['task_id']}] {n['status']}: {n['result']}"
                    for n in notifs
                )
                messages.append({
                    "role": "user",
                    "content": f"<background-results>\n{text}\n</background-results>",
                })

        # ── Lead inbox 检查 ────────────────────────────────────
        if team_bus is not None:
            inbox = team_bus.read_inbox("lead")
            if inbox:
                print("=========inboxInfo: ", inbox)
                messages.append({
                    "role": "user",
                    "content": f"<inbox>{json.dumps(inbox, indent=2, ensure_ascii=False)}</inbox>",
                })

        # ── LLM 调用 ───────────────────────────────────────────
        response = client.chat_stream(
            messages=messages,
            system=system,
            tools=schemas,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return

        # ── 工具执行 ───────────────────────────────────────────
        results = []
        used_todo = False
        manual_compact = False

        for block in response.content:
            if block["type"] == "tool_use":
                print(f"\033[33m> {block['name']}\033[0m")
                if block["name"] == "compact":
                    # 标记手动压缩——在工具结果注入后再触发
                    manual_compact = True
                    output = "Compressing..."
                else:
                    output = tools_registry.dispatch(block["name"], block["input"])
                print(str(output)[:200])
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": output,
                })
                if block["name"] == "TodoWrite":
                    used_todo = True

        # ── Todo nag reminder ──────────────────────────────────
        if todo_manager is not None:
            rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
            if todo_manager.has_open_items() and rounds_since_todo >= 3:
                results.append({
                    "type": "text",
                    "text": "<reminder>请更新你的 Todo 列表。</reminder>",
                })

        messages.append({"role": "user", "content": results})

        # ── Layer 3: manual compact — LLM 主动触发 ────────────
        if manual_compact and compact_manager is not None:
            print("[manual compact]")
            compacted = compact_manager.compact(messages)
            if compacted is not None:
                messages[:] = compacted
                return  # 压缩后退出本轮，用户可继续发起新对话
