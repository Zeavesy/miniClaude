"""
LLM API 抽象层。
目前只支持 Anthropic 协议，后续可扩展为多 provider。
"""

import json
import os
from types import SimpleNamespace

from anthropic import Anthropic
from dotenv import load_dotenv


class LLMClient:
    """封装 Anthropic SDK，提供统一的 chat 接口。"""

    def __init__(self):
        load_dotenv(override=True)

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("未找到 ANTHROPIC_API_KEY，请在 .env 中配置")

        self.model = os.getenv("MODEL_ID", "claude-sonnet-4-6")
        base_url = os.getenv("ANTHROPIC_BASE_URL")

        if base_url:
            self._client = Anthropic(base_url=base_url)
        else:
            self._client = Anthropic(api_key=api_key)

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 8000,
    ):
        """
        调用 LLM 返回响应对象（Anthropic Message 对象）。

        参数:
            messages:  对话历史，格式 [{"role": "user/assistant", "content": ...}]
            system:    系统提示词
            tools:     工具 schema 列表（Anthropic 格式）
            max_tokens:最大输出 token 数
        """
        kwargs = dict(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
        return self._client.messages.create(**kwargs)

    def chat_stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 8000,
    ):
        """
        流式版 chat()：文本实时输出到终端，tool_use 完整后返回。

        返回 SimpleNamespace(content=[...], stop_reason=str)
        content 中的每个 block 为 dict，兼容 agent_loop 的 [] 访问。
        """
        kwargs = dict(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools

        stream = self._client.messages.create(**kwargs)

        blocks: list[dict] = []
        cur_type = ""
        cur_text = ""
        cur_tool_id = ""
        cur_tool_name = ""
        cur_tool_input = ""
        stop_reason = ""

        for event in stream:
            etype = event.type

            if etype == "content_block_start":
                cb = event.content_block
                if cb.type == "text":
                    cur_type = "text"
                    cur_text = cb.text
                elif cb.type == "tool_use":
                    cur_type = "tool_use"
                    cur_tool_id = cb.id
                    cur_tool_name = cb.name
                    cur_tool_input = ""

            elif etype == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    cur_text += delta.text
                    print(delta.text, end="", flush=True)
                elif delta.type == "input_json_delta":
                    cur_tool_input += delta.partial_json

            elif etype == "content_block_stop":
                if cur_type == "text":
                    blocks.append({"type": "text", "text": cur_text})
                    print()  # 文本块结束换行
                elif cur_type == "tool_use":
                    try:
                        inp = json.loads(cur_tool_input)
                    except json.JSONDecodeError:
                        inp = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": cur_tool_id,
                        "name": cur_tool_name,
                        "input": inp,
                    })

            elif etype == "message_delta":
                stop_reason = event.delta.stop_reason or ""

        return SimpleNamespace(content=blocks, stop_reason=stop_reason)

    def estimate_tokens(self, messages: list[dict]) -> int:
        """粗略估算 token 数：~4 字符/token。"""
        return len(str(messages)) // 4
