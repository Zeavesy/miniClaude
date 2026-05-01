"""
工具注册表 —— 纯注册与分发逻辑，不包含任何工具实现。
工具实现位于 tools/ 目录下。
"""
import time
from pathlib import Path

from tools import run_bash, run_read, run_write, run_edit, run_glob
from managers import TodoManager, TaskManager, BackgroundManager


class ToolRegistry:
    """统一管理工具：注册 → Schema 生成 → 分发执行。"""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, handler, properties: dict,
                 required: list[str] = None):
        self._tools[name] = {
            "name": name,
            "description": description,
            "handler": handler,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        }

    def get_schemas(self) -> list[dict]:
        return [
            {"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]}
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, inputs: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"未知工具: {name}"
        start = time.time()
        try:
            result = tool["handler"](**inputs)
        except Exception as e:
            result = f"Error: {e}"
        elapsed = (time.time() - start) * 1000
        if len(str(result)) > 500:
            print(f"  [{name}] {len(str(result))} 字节, {elapsed:.0f}ms")
        return str(result)

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


# ── 全局注册表 + 全部工具注册 ────────────────────────────────

WORKDIR = Path.cwd()

# Manager 实例（供工具 handler 闭包捕获）
todo_mgr = TodoManager()
task_mgr = TaskManager(WORKDIR / ".tasks")
bg_mgr = BackgroundManager(WORKDIR)

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
