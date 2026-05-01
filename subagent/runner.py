"""
SubAgent Runner —— 用全新 messages=[] 启动子代理执行任务。

核心思想（来自原项目 s04）:
    "Process isolation gives context isolation for free."

    父代理                       子代理
    ┌──────────────────┐        ┌──────────────────┐
    │ messages=[......] │        │ messages=[]      │  ← 全新上下文
    │ 工具: task        │───────>│ 工具: bash/read  │
    │   prompt="..."    │        │       /write/edit│
    │                  │ 摘要   │                  │
    │   result = "..."  │<───────│ return last text │
    └──────────────────┘        └──────────────────┘
              │
    父上下文保持干净；子上下文用完即弃。

与 Teammate 的区别:
    SubAgent: spawn → execute → return summary → destroyed（一次性）
    Teammate: spawn → work → idle → work → ...（持久化，后续实现）
"""

from pathlib import Path

from core.llm_client import LLMClient
from core.tool_registry import ToolRegistry
from tools import run_bash, run_read, run_write, run_edit, run_glob

# 子代理的 system prompt — 强调任务完成 + 摘要返回
SUBAGENT_SYSTEM = "You are a coding subagent at {workdir}. Complete the given task, then summarize your findings concisely."

# 子代理最大轮数 — 防止无限循环
MAX_ROUNDS = 30


def _make_child_registry() -> ToolRegistry:
    """
    子代理工具集: 基础 5 工具，不含 task（防止递归 spawn 子代理的子代理）。

    与父代理共享文件系统（同一 WORKDIR），但上下文隔离。
    """
    reg = ToolRegistry()
    reg.register("bash", "", run_bash,
                 {"command": {"type": "string"}}, ["command"])
    reg.register("read_file", "", run_read,
                 {"path": {"type": "string"}, "limit": {"type": "integer"}}, ["path"])
    reg.register("write_file", "", run_write,
                 {"path": {"type": "string"}, "content": {"type": "string"}},
                 ["path", "content"])
    reg.register("edit_file", "", run_edit,
                 {"path": {"type": "string"}, "old_text": {"type": "string"},
                  "new_text": {"type": "string"}}, ["path", "old_text", "new_text"])
    reg.register("glob", "", run_glob,
                 {"pattern": {"type": "string"}, "path": {"type": "string"}}, ["pattern"])
    return reg


def run_subagent(
    prompt: str,
    client: LLMClient = None,
    workdir: Path = None,
) -> str:
    """
    启动子代理执行任务，返回摘要字符串。

    参数:
        prompt:  子代理的任务描述。父代理调用 task 工具时传入。
        client:  LLM 客户端。为 None 则自动创建。
        workdir: 工作目录。为 None 则取 Path.cwd()。

    返回:
        子代理最后一条文本响应作为摘要；如果子代理无文本输出则返回 "(无摘要)"。

    安全保护:
        - 最多 MAX_ROUNDS (30) 轮
        - 不含 task 工具，防止递归嵌套
        - 子代理异常时返回错误信息而非崩溃
    """
    if client is None:
        client = LLMClient()
    if workdir is None:
        workdir = Path.cwd()

    registry = _make_child_registry()
    schemas = registry.get_schemas()
    system = SUBAGENT_SYSTEM.format(workdir=workdir)

    # 子代理拥有全新上下文——这是核心价值
    messages = [{"role": "user", "content": prompt}]

    response = None
    try:
        for _ in range(MAX_ROUNDS):
            response = client.chat(
                messages=messages,
                system=system,
                tools=schemas,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = registry.dispatch(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(output)[:50000],
                    })
            messages.append({"role": "user", "content": results})
    except Exception as e:
        return f"(子代理异常: {e})"

    # 子代理上下文被丢弃——只有摘要返回给父代理
    if response is not None:
        text_blocks = [b for b in response.content if hasattr(b, "text")]
        summary = "".join(b.text for b in text_blocks)
        return summary.strip() if summary.strip() else "(无摘要)"
    return "(无摘要)"
