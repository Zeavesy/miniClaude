"""
工具箱 —— 全局 Manager 实例 + 全部 20 个工具注册。
ToolRegistry 类定义在 core/tool_registry.py 中（因 subagent 也需使用，避免循环导入）。
"""
import json
from pathlib import Path

from core.llm_client import LLMClient
from core.tool_registry import ToolRegistry
from tools import run_bash, run_read, run_write, run_edit, run_glob
from managers import TodoManager, TaskManager, BackgroundManager
from skills import SkillLoader
from subagent import run_subagent
from team import MessageBus, TeammateManager
from team.message_bus import VALID_MSG_TYPES
from team.protocols import handle_shutdown_request, check_shutdown_status, handle_plan_review


# ── 全局注册表 + 全部工具注册 ────────────────────────────────

WORKDIR = Path.cwd()

# Manager 实例（供工具 handler 闭包捕获）
todo_mgr = TodoManager()
task_mgr = TaskManager(WORKDIR / ".tasks")
bg_mgr = BackgroundManager(WORKDIR)
skill_loader = SkillLoader(WORKDIR / "skills")
team_bus = MessageBus(WORKDIR / ".team" / "inbox")
team_mgr = TeammateManager(WORKDIR / ".team", team_bus)

registry = ToolRegistry()

# ── 基础工具（tools/）────────────────────────────────────────

registry.register("bash", "执行 Shell 命令（阻塞），超时 120s。", run_bash,
                  {"command": {"type": "string"}},
                  required=["command"])

registry.register("read_file", "读取文件内容，可选 limit 限制行数。", run_read,
                  {"path": {"type": "string"}, "limit": {"type": "integer"}},
                  required=["path"])

registry.register("write_file", "将内容写入文件（自动创建父目录）。", run_write,
                  {"path": {"type": "string"}, "content": {"type": "string"}},
                  required=["path", "content"])

registry.register("edit_file", "替换文件中的精确文本（首个匹配）。", run_edit,
                  {"path": {"type": "string"}, "old_text": {"type": "string"},
                   "new_text": {"type": "string"}},
                  required=["path", "old_text", "new_text"])

registry.register("glob", "按 glob 模式匹配文件（如 **/*.py）。", run_glob,
                  {"pattern": {"type": "string"}, "path": {"type": "string"}},
                  required=["pattern"])

# ── Todo 工具（managers/todo_manager）─────────────────────────

registry.register("TodoWrite", "更新任务进度列表。每项含 content/status，in_progress 时建议填 activeForm。",
                  lambda **kw: todo_mgr.update(kw["items"]),
                  {"items": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "content": {"type": "string"},
                              "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                              "activeForm": {"type": "string", "description": "in_progress 时的进行中描述"},
                          },
                          "required": ["content", "status"],
                      },
                  }},
                  required=["items"])

# ── Task 工具（managers/task_manager）─────────────────────────

registry.register("task_create", "创建持久化任务。",
                  lambda **kw: task_mgr.create(kw["subject"], kw.get("description", "")),
                  {"subject": {"type": "string"}, "description": {"type": "string"}},
                  required=["subject"])

registry.register("task_get", "查看任务详情。",
                  lambda **kw: task_mgr.get(kw["task_id"]),
                  {"task_id": {"type": "integer"}},
                  required=["task_id"])

registry.register("task_update", "更新任务状态或依赖关系。",
                  lambda **kw: task_mgr.update(
                      kw["task_id"], kw.get("status"),
                      kw.get("addBlockedBy"), kw.get("removeBlockedBy"),
                  ),
                  {"task_id": {"type": "integer"},
                   "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                   "addBlockedBy": {"type": "array", "items": {"type": "integer"}},
                   "removeBlockedBy": {"type": "array", "items": {"type": "integer"}}},
                  required=["task_id"])

registry.register("task_list", "列出所有任务及状态。",
                  lambda **kw: task_mgr.list_all(),
                  {})

# ── Background 工具（managers/background_manager）─────────────

registry.register("background_run", "在后台线程中执行耗时命令，立即返回 task_id。",
                  lambda **kw: bg_mgr.run(kw["command"], kw.get("timeout", 300)),
                  {"command": {"type": "string"}, "timeout": {"type": "integer"}},
                  required=["command"])

registry.register("check_background", "查询后台任务状态。省略 task_id 则列出所有。",
                  lambda **kw: bg_mgr.check(kw.get("task_id")),
                  {"task_id": {"type": "string"}})

# ── Compact 工具（context/compact）────────────────────────────
# 实际压缩逻辑在 agent_loop 中——这里只返回一个占位确认

registry.register("compact", "手动触发对话压缩。长对话时可主动调用以释放上下文窗口。",
                  lambda **kw: "Compressing...",
                  {"focus": {"type": "string", "description": "希望在摘要中重点保留的内容"}})

# ── Skill 工具（skills/loader）────────────────────────────────

registry.register("load_skill", "按需加载技能知识。传入技能名，返回完整的领域指导文档。",
                  lambda **kw: skill_loader.get_content(kw["name"]),
                  {"name": {"type": "string", "description": "要加载的技能名称"}},
                  required=["name"])

# ── Team 工具（team/）────────────────────────────────────────

registry.register("spawn_teammate", "启动一个命名队友线程。队友在后台运行，通过 inbox 通信。",
                  lambda **kw: team_mgr.spawn(kw["name"], kw["role"], kw["prompt"]),
                  {"name": {"type": "string"}, "role": {"type": "string"},
                   "prompt": {"type": "string"}},
                  required=["name", "role", "prompt"])

registry.register("list_teammates", "列出所有队友及其状态（name/role/status）。",
                  lambda **kw: team_mgr.list_all(),
                  {})

registry.register("send_message", "向指定队友的 inbox 发送消息。",
                  lambda **kw: team_bus.send("lead", kw["to"], kw["content"],
                                              kw.get("msg_type", "message")),
                  {"to": {"type": "string"}, "content": {"type": "string"},
                   "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}},
                  required=["to", "content"])

registry.register("read_inbox", "读取并清空 lead 的 inbox。",
                  lambda **kw: json.dumps(team_bus.read_inbox("lead"), indent=2, ensure_ascii=False),
                  {})

registry.register("broadcast", "向所有队友发送广播消息。",
                  lambda **kw: team_bus.broadcast("lead", kw["content"], team_mgr.member_names()),
                  {"content": {"type": "string"}},
                  required=["content"])

# ── Team Protocols 工具（team/protocols）───────────────────────

registry.register("shutdown_request", "向指定队友发送关机请求。返回 request_id 用于追踪状态。",
                  lambda **kw: handle_shutdown_request(kw["teammate"], team_bus),
                  {"teammate": {"type": "string"}},
                  required=["teammate"])

registry.register("shutdown_response", "查询关机请求的状态（按 request_id）。",
                  lambda **kw: check_shutdown_status(kw.get("request_id", "")),
                  {"request_id": {"type": "string"}},
                  required=["request_id"])

registry.register("plan_approval", "审查队友提交的计划：approve=true 批准，false 拒绝，可选 feedback。",
                  lambda **kw: handle_plan_review(kw["request_id"], kw["approve"],
                                                   kw.get("feedback", ""), team_bus),
                  {"request_id": {"type": "string"}, "approve": {"type": "boolean"},
                   "feedback": {"type": "string"}},
                  required=["request_id", "approve"])

# ── SubAgent 工具（subagent/runner）────────────────────────────

_registry_client = None  # 由 main.py 注入，供 task handler 使用

def _get_client():
    global _registry_client
    if _registry_client is None:
        _registry_client = LLMClient()
    return _registry_client

# 允许 main.py 注入共享 client
def set_registry_client(client):
    global _registry_client
    _registry_client = client

registry.register("task", "派生子代理执行任务。子代理拥有全新上下文（messages=[]），与父代理共享文件系统，完成后返回摘要。适合需要上下文隔离的探索或子任务。",
                  lambda **kw: run_subagent(kw["prompt"], _get_client(), WORKDIR),
                  {"prompt": {"type": "string", "description": "子代理的任务描述"},
                   "description": {"type": "string", "description": "任务简短描述"}},
                  required=["prompt"])
