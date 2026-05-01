"""
CompactManager — 三层上下文压缩管道，防止消息窗口越界。

三层策略:

    Layer 1: micro_compact（静默，每轮自动执行）
        把旧的非 read_file 工具结果替换为占位符，保留最近 KEEP_RECENT 条。
        目标: 不让 verbose 的 bash 输出堆满上下文。

    Layer 2: auto_compact（超阈值自动触发）
        当 estimate_tokens > THRESHOLD 时:
          1) 保存完整对话到 .transcripts/transcript_<ts>.jsonl
          2) 调 LLM 生成摘要
          3) 用摘要替换全部 messages

    Layer 3: manual compact（LLM 主动调用 compact 工具触发）
        与 auto_compact 逻辑相同，由 LLM 在工具调用中发起。

设计原则:
    - read_file 的结果是参考资料，压缩它会导致 LLM 反复重读，反而浪费 token
    - KEEP_RECENT 默认 3 条，保证 LLM 至少能看到最近的工具输出上下文
    - 摘要调用用单独的小型 LLM 请求（max_tokens=2000），不污染主对话
"""

import json
import time
from pathlib import Path


class CompactManager:
    def __init__(self, workdir: Path, llm_client=None):
        """
        workdir:    工作区根目录，.transcripts/ 将创建在此
        llm_client: 用于 auto/manual compact 的摘要 LLM 调用
        """
        self.workdir = workdir
        self._client = llm_client  # 延迟注入，避免循环导入
        self.transcript_dir = workdir / ".transcripts"
        self.threshold = 100000       # 超过此 token 估算值则触发 auto_compact
        self.keep_recent = 3          # micro_compact 保留最近 N 条工具结果
        self.preserve_tools = {"read_file"}  # 这些工具的结果永不压缩

    def set_client(self, client):
        """延迟注入 LLMClient，避免与 core.llm_client 的循环导入。"""
        self._client = client

    # ═══════════════════════════════════════════════════════════
    # Layer 1: 静默压缩 — 每轮自动执行
    # ═══════════════════════════════════════════════════════════

    def micro_compact(self, messages: list[dict]):
        """
        找到所有 tool_result，保留最近 keep_recent 条，
        把更早的非 read_file 结果替换为 "[Previous: used {tool_name}]"。

        该函数原地修改 messages（副作用），不返回值。
        """
        # 第一步: 收集所有 tool_result 的位置信息
        tool_results = []
        for msg_idx, msg in enumerate(messages):
            if msg["role"] == "user" and isinstance(msg.get("content"), list):
                for part_idx, part in enumerate(msg["content"]):
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        tool_results.append((msg_idx, part_idx, part))

        if len(tool_results) <= self.keep_recent:
            return  # 条数不多，无需压缩

        # 第二步: 从 assistant 消息中建立 tool_use_id → tool_name 的映射
        # 这样才能知道每个 tool_result 来自哪个工具
        tool_name_map = {}
        for msg in messages:
            if msg["role"] == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            tool_name_map[block.id] = block.name

        # 第三步: 对前 N - keep_recent 条旧结果做替换
        to_clear = tool_results[:-self.keep_recent]
        for _, _, result in to_clear:
            # 跳过短结果——不值得替换
            if not isinstance(result.get("content"), str) or len(result["content"]) <= 100:
                continue
            tool_id = result.get("tool_use_id", "")
            tool_name = tool_name_map.get(tool_id, "unknown")
            # read_file 结果保留——它们是参考资料，压缩会导致反复重读
            if tool_name in self.preserve_tools:
                continue
            result["content"] = f"[Previous: used {tool_name}]"

    # ═══════════════════════════════════════════════════════════
    # Layer 2 & 3: 完整压缩 — 保存 + 摘要 + 替换
    # ═══════════════════════════════════════════════════════════

    def compact(self, messages: list[dict]) -> list[dict] | None:
        """
        执行完整压缩:

        1. 保存完整对话到 .transcripts/transcript_<timestamp>.jsonl
        2. 调用 LLM 生成摘要
        3. 返回新的 messages（只含摘要），调用方用它替换原 messages

        如果 _client 未注入或调用失败，返回 None。
        """
        if self._client is None:
            return None

        # 存盘
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = self.transcript_dir / f"transcript_{int(time.time())}.jsonl"
        with open(transcript_path, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, default=str) + "\n")

        # 取最后 80000 字符给 LLM 作摘要输入
        conversation_text = json.dumps(messages, default=str)[-80000:]
        try:
            response = self._client.chat(
                messages=[{"role": "user", "content":
                    "Summarize this conversation for continuity. Include: "
                    "1) What was accomplished, 2) Current state, 3) Key decisions made. "
                    "Be concise but preserve critical details.\n\n" + conversation_text}],
                max_tokens=2000,
            )
            summary = ""
            if hasattr(response, "content"):
                for block in response.content:
                    if hasattr(block, "text"):
                        summary += block.text
            if not summary.strip():
                summary = "(summary unavailable)"
        except Exception:
            summary = "(compression failed)"

        print(f"[compact] transcript saved: {transcript_path}")

        # 返回压缩后的 messages——只有一条摘要
        return [
            {"role": "user",
             "content": f"[Conversation compressed. Transcript: {transcript_path}]\n\n{summary}"},
        ]

    # ═══════════════════════════════════════════════════════════
    # 管道入口 — agent_loop 调用此方法
    # ═══════════════════════════════════════════════════════════

    def should_compact(self, messages: list[dict]) -> bool:
        """检查是否超过阈值，需要触发 auto_compact。"""
        if self._client is None:
            return False
        return self._client.estimate_tokens(messages) > self.threshold
