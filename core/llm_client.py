"""
LLM API 抽象层。
目前只支持 Anthropic 协议，后续可扩展为多 provider。
"""

import os
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

    def estimate_tokens(self, messages: list[dict]) -> int:
        """粗略估算 token 数：~4 字符/token。"""
        return len(str(messages)) // 4
