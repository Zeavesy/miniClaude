"""
WorktreeManager + EventBus — Git Worktree 目录级任务隔离。

核心概念（原项目 key insight）:
    "Isolate by directory, coordinate by task ID."
    任务 = 控制面，worktree = 执行面。

存储:
    .worktrees/index.json  — worktree 注册表
    .worktrees/events.jsonl — 生命周期事件日志

EventBus: 所有 create/remove/keep 操作产生事件追加到 events.jsonl。
WorktreeManager: 基于 git worktree 的 CRUD + 命令执行。
"""

import json
import re
import subprocess
import time
from pathlib import Path


# ══════════════════════════════════════════════════════════════
# EventBus — 追加式生命周期事件日志
# ══════════════════════════════════════════════════════════════

class EventBus:
    def __init__(self, event_log_path: Path):
        self.path = event_log_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, task: dict = None, worktree: dict = None,
             error: str = None):
        payload = {
            "event": event,
            "ts": time.time(),
            "task": task or {},
            "worktree": worktree or {},
        }
        if error:
            payload["error"] = error
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def list_recent(self, limit: int = 20) -> str:
        n = max(1, min(int(limit or 20), 200))
        lines = self.path.read_text(encoding="utf-8").splitlines()
        recent = lines[-n:]
        items = []
        for line in recent:
            try:
                items.append(json.loads(line))
            except Exception:
                items.append({"event": "parse_error", "raw": line})
        return json.dumps(items, indent=2)


# ══════════════════════════════════════════════════════════════
# WorktreeManager
# ══════════════════════════════════════════════════════════════

class WorktreeManager:
    def __init__(self, repo_root: Path, tasks, events: EventBus):
        self.repo_root = repo_root
        self.tasks = tasks      # TaskManager 实例（用于 bind/unbind）
        self.events = events
        self.dir = repo_root / ".worktrees"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.json"
        if not self.index_path.exists():
            self.index_path.write_text(
                json.dumps({"worktrees": []}, indent=2), encoding="utf-8")
        self.git_available = self._is_git_repo()

    def _is_git_repo(self) -> bool:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.repo_root, capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _run_git(self, args: list[str]) -> str:
        if not self.git_available:
            raise RuntimeError("不在 git 仓库中。worktree 工具需要 git。")
        r = subprocess.run(
            ["git", *args], cwd=self.repo_root,
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            msg = (r.stdout + r.stderr).strip()
            raise RuntimeError(msg or f"git {' '.join(args)} 失败")
        return (r.stdout + r.stderr).strip() or "(无输出)"

    def _load_index(self) -> dict:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, data: dict):
        self.index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _find(self, name: str) -> dict | None:
        idx = self._load_index()
        for wt in idx.get("worktrees", []):
            if wt.get("name") == name:
                return wt
        return None

    def _validate_name(self, name: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", name or ""):
            raise ValueError("worktree 名称无效：1-40 字符，仅字母数字 . _ -")

    # ── 公共接口 ────────────────────────────────────────────

    def create(self, name: str, task_id: int = None, base_ref: str = "HEAD") -> str:
        self._validate_name(name)
        if self._find(name):
            raise ValueError(f"Worktree '{name}' 已存在")
        if task_id is not None and not self.tasks.exists(task_id):
            raise ValueError(f"Task {task_id} 不存在")

        path = self.dir / name
        branch = f"wt/{name}"

        self.events.emit("worktree.create.before",
                         task={"id": task_id} if task_id else {},
                         worktree={"name": name, "base_ref": base_ref})

        try:
            self._run_git(["worktree", "add", "-b", branch, str(path), base_ref])
        except Exception as e:
            self.events.emit("worktree.create.failed",
                             worktree={"name": name}, error=str(e))
            raise

        entry = {
            "name": name, "path": str(path), "branch": branch,
            "task_id": task_id, "status": "active",
            "created_at": time.time(),
        }
        idx = self._load_index()
        idx["worktrees"].append(entry)
        self._save_index(idx)

        if task_id is not None:
            self.tasks.bind_worktree(task_id, name)

        self.events.emit("worktree.create.after",
                         task={"id": task_id} if task_id else {},
                         worktree={"name": name, "status": "active"})
        return json.dumps(entry, indent=2)

    def list_all(self) -> str:
        idx = self._load_index()
        wts = idx.get("worktrees", [])
        if not wts:
            return "暂无 worktree。"
        lines = []
        for wt in wts:
            suffix = f" task={wt['task_id']}" if wt.get("task_id") else ""
            lines.append(f"[{wt.get('status', '?')}] {wt['name']} "
                         f"-> {wt['path']} ({wt.get('branch', '-')}){suffix}")
        return "\n".join(lines)

    def status(self, name: str) -> str:
        wt = self._find(name)
        if not wt:
            return f"Error: 未知 worktree '{name}'"
        path = Path(wt["path"])
        if not path.exists():
            return f"Error: worktree 路径不存在: {path}"
        r = subprocess.run(["git", "status", "--short", "--branch"],
                           cwd=path, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip() or "Clean worktree"

    def run(self, name: str, command: str) -> str:
        dangerous = ["rm -rf /", "sudo", "shutdown", "reboot"]
        if any(d in command for d in dangerous):
            return "Error: 危险命令被拦截"

        wt = self._find(name)
        if not wt:
            return f"Error: 未知 worktree '{name}'"
        path = Path(wt["path"])
        if not path.exists():
            return f"Error: worktree 路径不存在: {path}"

        try:
            r = subprocess.run(command, shell=True, cwd=path,
                               capture_output=True, text=True, timeout=300)
            out = (r.stdout + r.stderr).strip()
            return out[:50000] if out else "(无输出)"
        except subprocess.TimeoutExpired:
            return "Error: 超时 (300s)"

    def remove(self, name: str, force: bool = False, complete_task: bool = False) -> str:
        wt = self._find(name)
        if not wt:
            return f"Error: 未知 worktree '{name}'"

        self.events.emit("worktree.remove.before",
                         task={"id": wt.get("task_id")} if wt.get("task_id") else {},
                         worktree={"name": name})

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(wt["path"])
        try:
            self._run_git(args)
        except Exception as e:
            self.events.emit("worktree.remove.failed",
                             worktree={"name": name}, error=str(e))
            raise

        if complete_task and wt.get("task_id") is not None:
            self.tasks.update(wt["task_id"], status="completed")
            self.tasks.unbind_worktree(wt["task_id"])

        idx = self._load_index()
        for item in idx.get("worktrees", []):
            if item.get("name") == name:
                item["status"] = "removed"
                item["removed_at"] = time.time()
        self._save_index(idx)

        self.events.emit("worktree.remove.after",
                         worktree={"name": name, "status": "removed"})
        return f"Removed worktree '{name}'"

    def keep(self, name: str) -> str:
        wt = self._find(name)
        if not wt:
            return f"Error: 未知 worktree '{name}'"

        idx = self._load_index()
        for item in idx.get("worktrees", []):
            if item.get("name") == name:
                item["status"] = "kept"
                item["kept_at"] = time.time()
        self._save_index(idx)

        self.events.emit("worktree.keep",
                         worktree={"name": name, "status": "kept"})
        return json.dumps(wt, indent=2)
