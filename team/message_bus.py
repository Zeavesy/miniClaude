"""
MessageBus — 基于 JSONL 文件的队友间消息通信。

每个队友一个 inbox 文件: .team/inbox/{name}.jsonl
send(): 追加一行 JSON 到目标文件
read_inbox(): 读取全部 → 清空文件（drain 语义）
broadcast(): 给除发送者外的所有人发

消息类型（s10/s11 会用更多，s09 先声明):
    message        — 普通文本消息
    broadcast      — 广播消息
    shutdown_request / shutdown_response (s10)
    plan_approval_response (s10)
"""

import json
import time
from pathlib import Path

VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
    "shutdown_response",
    "plan_approval_response",
}


class MessageBus:
    def __init__(self, inbox_dir: Path):
        self.dir = inbox_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        """向指定队友的 inbox 追加一条消息。"""
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: 无效消息类型 '{msg_type}'。可选: {VALID_MSG_TYPES}"

        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)

        inbox_path = self.dir / f"{to}.jsonl"
        with open(inbox_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list[dict]:
        """读取并清空指定队友的 inbox（drain 语义）。"""
        inbox_path = self.dir / f"{name}.jsonl"
        if not inbox_path.exists():
            return []

        messages = []
        for line in inbox_path.read_text(encoding="utf-8").strip().splitlines():
            if line:
                messages.append(json.loads(line))
        inbox_path.write_text("")  # drain
        return messages

    def broadcast(self, sender: str, content: str, teammates: list[str]) -> str:
        """给除 sender 外的所有队友发广播。"""
        count = 0
        for name in teammates:
            if name != sender:
                self.send(sender, name, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"
