"""
TaskManager — JSON 文件持久化的长期任务系统。

定位:
    用来回答"这个项目还有哪些事要做？"——存盘事项，跨对话存活。
    适合多轮对话、需要几天才能完成的大任务。

与 TodoManager 的分工:
    TodoManager:  短期，活在当前对话里，进程退出就没了
    TaskManager:  长期，落盘为 .tasks/task_<id>.json，下次运行 python main.py 还能看到

"""

import json
from pathlib import Path


class TaskManager:
    def __init__(self, tasks_dir: Path):
        """
        tasks_dir: 任务文件存储目录，通常为 <workspace>/.tasks/
        目录不存在时自动创建。
        """
        self.dir = tasks_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        # 自增 ID: 从现有文件中找到最大 ID + 1
        self._next_id = self._max_id() + 1

    # ═══════════════════════════════════════════════════════════
    # 内部辅助 — 文件系统操作
    # ═══════════════════════════════════════════════════════════

    def _max_id(self) -> int:
        """扫描 .tasks/ 目录，找到当前最大的 task ID。"""
        ids = []
        for f in self.dir.glob("task_*.json"):
            try:
                ids.append(int(f.stem.split("_")[1]))
            except ValueError:
                pass  # 跳过命名不合规的文件
        return max(ids) if ids else 0

    def _path(self, task_id: int) -> Path:
        """返回任务文件的完整路径。"""
        return self.dir / f"task_{task_id}.json"

    def _load(self, task_id: int) -> dict:
        """从文件加载单个任务，不存在时抛出。"""
        path = self._path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} 不存在")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, task: dict):
        """将任务对象写入 JSON 文件。"""
        self._path(task["id"]).write_text(
            json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _clear_dependency(self, completed_id: int):
        """
        依赖图自动清理的核心:

        当某个任务被标记为 completed 时，遍历所有其他任务文件，
        从它们的 blockedBy 列表中移除该 completed_id。
        这意味着: 一旦前置任务完成，下游任务自动解除阻塞。
        """
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text(encoding="utf-8"))
            if completed_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_id)
                self._save(task)

    # ═══════════════════════════════════════════════════════════
    # 公共接口 — 对应 task_create / task_get / task_update / task_list
    # ═══════════════════════════════════════════════════════════

    def create(self, subject: str, description: str = "") -> str:
        """
        创建一个新任务（初始状态: pending，无依赖）。

        返回: 新任务的 JSON 字符串（作为 tool_result 给 LLM）。
        """
        task = {
            "id": self._next_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "worktree": "",
        }
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, task_id: int) -> str:
        """查看单个任务详情。"""
        return json.dumps(self._load(task_id), indent=2, ensure_ascii=False)

    def update(self, task_id: int, status: str = None,
               add_blocked_by: list[int] = None,
               remove_blocked_by: list[int] = None) -> str:
        """
        更新任务状态或依赖关系。

        三个操作可以同时做:
          - status:         修改任务状态
          - add_blocked_by: 添加依赖（传入 task id 列表）
          - remove_blocked_by: 移除依赖

        特殊行为: 当 status 设为 "completed" 时，自动触发 _clear_dependency()
                  解除所有下游任务对该任务的阻塞。
        """
        task = self._load(task_id)

        if status:
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"无效状态: {status}")
            task["status"] = status
            if status == "completed":
                # 下游任务自动解除阻塞
                self._clear_dependency(task_id)

        if add_blocked_by:
            # 去重合并，避免同名 id 重复出现在列表中
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))

        if remove_blocked_by:
            task["blockedBy"] = [x for x in task["blockedBy"] if x not in remove_blocked_by]

        self._save(task)
        return json.dumps(task, indent=2, ensure_ascii=False)

    def list_all(self) -> str:
        """
        列出所有任务（按文件自然排序），带进度标记。

        输出示例:
            [ ] #1: 重构认证模块
            [>] #2: 添加日志系统 (依赖: [1])
            [x] #3: 写单元测试

            (1/3 完成)
        """
        tasks = []
        for f in sorted(self.dir.glob("task_*.json")):
            tasks.append(json.loads(f.read_text(encoding="utf-8")))

        if not tasks:
            return "暂无任务。"

        lines = []
        for t in tasks:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(t["status"], "[?]")
            blocked = f" (依赖: {t['blockedBy']})" if t.get("blockedBy") else ""
            wt = f" wt={t['worktree']}" if t.get("worktree") else ""
            lines.append(f"{marker} #{t['id']}: {t['subject']}{blocked}{wt}")

        done = sum(1 for t in tasks if t["status"] == "completed")
        lines.append(f"\n({done}/{len(tasks)} 完成)")
        return "\n".join(lines)

    # ── s12: worktree 绑定 ─────────────────────────────────

    def exists(self, task_id: int) -> bool:
        return self._path(task_id).exists()

    def bind_worktree(self, task_id: int, worktree: str, owner: str = "") -> str:
        task = self._load(task_id)
        task["worktree"] = worktree
        if owner:
            task["owner"] = owner
        if task["status"] == "pending":
            task["status"] = "in_progress"
        self._save(task)
        return json.dumps(task, indent=2, ensure_ascii=False)

    def unbind_worktree(self, task_id: int) -> str:
        task = self._load(task_id)
        task["worktree"] = ""
        self._save(task)
        return json.dumps(task, indent=2, ensure_ascii=False)
