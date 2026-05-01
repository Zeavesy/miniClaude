"""
TeammateManager — 持久化命名队友的线程管理。

每个队友是一个 daemon 线程，内部跑精简的 agent_loop。
生命周期: spawn → working → idle → (可选)shutdown
状态持久化到 .team/config.json

与 SubAgent 的区别:
    SubAgent:  spawn → execute → return summary → destroyed（一次性）
    Teammate:  spawn → work → inbox check → work → ...（持久化）
"""

import json
import threading
import time
import uuid
from pathlib import Path

from core.llm_client import LLMClient
from core.tool_registry import ToolRegistry
from tools import run_bash, run_read, run_write, run_edit, run_glob
from team.message_bus import MessageBus, VALID_MSG_TYPES
from team.protocols import shutdown_requests, plan_requests, _tracker_lock


class TeammateManager:
    def __init__(self, team_dir: Path, bus: MessageBus, client: LLMClient = None):
        self.dir = team_dir
        self.dir.mkdir(exist_ok=True)
        self.bus = bus
        self._client = client  # 延迟注入
        self.config_path = self.dir / "config.json"
        self.config = self._load_config()
        self.threads: dict[str, threading.Thread] = {}

    def set_client(self, client: LLMClient):
        self._client = client

    # ══════════════════════════════════════════════════════════
    # config.json 读写
    # ══════════════════════════════════════════════════════════

    def _load_config(self) -> dict:
        if self.config_path.exists():
            text = self.config_path.read_text(encoding="utf-8").strip()
            if text:
                return json.loads(text)
        return {"team_name": "default", "members": []}

    def _save_config(self):
        self.config_path.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _find_member(self, name: str) -> dict | None:
        for m in self.config["members"]:
            if m["name"] == name:
                return m
        return None

    def _set_status(self, name: str, status: str):
        m = self._find_member(name)
        if m:
            m["status"] = status
            self._save_config()

    # ══════════════════════════════════════════════════════════
    # 公共接口
    # ══════════════════════════════════════════════════════════

    def spawn(self, name: str, role: str, prompt: str) -> str:
        """启动一个命名队友线程。如果已处于 idle/shutdown，可复用。"""
        if self._client is None:
            return "Error: client 未注入，请先调用 set_client()"

        member = self._find_member(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' 当前状态为 {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save_config()

        t = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
        )
        self.threads[name] = t
        t.start()
        return f"Spawned '{name}' (role: {role})"

    def list_all(self) -> str:
        """列出所有队友及其状态。"""
        if not self.config["members"]:
            return "暂无队友。"
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list[str]:
        return [m["name"] for m in self.config["members"]]

    # ══════════════════════════════════════════════════════════
    # 队友线程循环
    # ══════════════════════════════════════════════════════════

    def _teammate_loop(self, name: str, role: str, prompt: str):
        """精简版 agent_loop：支持 shutdown_request 退出 + plan_approval 提交。"""
        sys_prompt = (
            f"You are '{name}', role: {role}. "
            # f"Submit plans via plan_approval before major work. "
            # f"Respond to shutdown_request with shutdown_response. "
            # f"Use send_message to communicate. Complete your task."
            f"RULES (text replies are invisible to the protocol — only tool calls count):\n"
            f"1. For risky/destructive work: FIRST call plan_approval tool with your plan. "
            f"Do NOT start work until lead approves via plan_approval_response.\n"
            f"2. On shutdown_request: IMMEDIATELY call shutdown_response tool with approve=true.\n"
            f"3. To communicate: call send_message tool. Never use plain text for important info.\n"
            f"Your first action after receiving any message MUST be a tool call, not text."
        )
        messages = [{"role": "user", "content": prompt}]
        tools = self._teammate_tools()

        should_exit = False
        for _ in range(50):
            inbox = self.bus.read_inbox(name)
            for msg in inbox:
                messages.append({"role": "user", "content": json.dumps(msg, ensure_ascii=False)})
            if should_exit:
                break

            try:
                response = self._client.chat(
                    messages=messages, system=sys_prompt, tools=tools,
                )
            except Exception:
                break

            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = self._exec_tool(name, block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(output),
                    })
                    # shutdown_response(approve=true) → 标记退出
                    if block.name == "shutdown_response" and block.input.get("approve"):
                        should_exit = True
            messages.append({"role": "user", "content": results})

        # 退出后标记最终状态
        member = self._find_member(name)
        if member:
            member["status"] = "shutdown" if should_exit else "idle"
            self._save_config()

    # ══════════════════════════════════════════════════════════
    # 队友工具集 + 分发
    # ══════════════════════════════════════════════════════════

    def _exec_tool(self, sender: str, tool_name: str, args: dict) -> str:
        if tool_name == "bash":
            return run_bash(args["command"])
        if tool_name == "read_file":
            return run_read(args["path"])
        if tool_name == "write_file":
            return run_write(args["path"], args["content"])
        if tool_name == "edit_file":
            return run_edit(args["path"], args["old_text"], args["new_text"])
        if tool_name == "send_message":
            return self.bus.send(sender, args["to"], args["content"],
                                 args.get("msg_type", "message"))
        if tool_name == "read_inbox":
            return json.dumps(self.bus.read_inbox(sender), indent=2, ensure_ascii=False)
        if tool_name == "shutdown_response":
            req_id = args["request_id"]
            approve = args["approve"]
            with _tracker_lock:
                if req_id in shutdown_requests:
                    shutdown_requests[req_id]["status"] = "approved" if approve else "rejected"
            self.bus.send(
                sender, "lead", args.get("reason", ""),
                "shutdown_response", {"request_id": req_id, "approve": approve},
            )
            return f"Shutdown {'approved' if approve else 'rejected'}"
        if tool_name == "plan_approval":
            plan_text = args.get("plan", "")
            req_id = str(uuid.uuid4())[:8]
            with _tracker_lock:
                plan_requests[req_id] = {"from": sender, "plan": plan_text, "status": "pending"}
            self.bus.send(
                sender, "lead", plan_text, "plan_approval_response",
                {"request_id": req_id, "plan": plan_text},
            )
            return f"Plan submitted (request_id={req_id}). Waiting for lead approval."
        return f"Unknown tool: {tool_name}"

    def _teammate_tools(self) -> list[dict]:
        """队友可用工具：5 基础 + send_message + read_inbox。"""
        return [
            {"name": "bash", "description": "Run a shell command.",
             "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file contents.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write content to file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Replace exact text in file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            {"name": "send_message", "description": "Send message to a teammate's inbox.",
             "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
            {"name": "read_inbox", "description": "Read and drain your inbox.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "shutdown_response", "description": "Respond to a shutdown request. Approve to shut down, reject to keep working.",
             "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["request_id", "approve"]}},
            {"name": "plan_approval", "description": "Submit a plan for lead approval. Provide plan text.",
             "input_schema": {"type": "object", "properties": {"plan": {"type": "string"}}, "required": ["plan"]}},
        ]
