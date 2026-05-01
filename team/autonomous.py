"""
Autonomous Agents — Teammate 自主生命周期。

WORK → IDLE → POLL 阶段机:

    ┌─────────┐  spawn  ┌─────────┐
    │  WORK   │ <────── │  IDLE   │
    │ (agent  │         │ (poll   │
    │  loop)  │ ──────> │  inbox/ │
    └─────────┘  idle   │  tasks) │
                        └────┬────┘
                             │ idle_timeout (60s)
                             v
                        (shutdown)

IDLE 阶段每 5s 轮询:
  1. 检查 inbox → 有新消息？→ resume WORK
  2. 扫描 .tasks/ → 有 unclaimed 任务？→ claim → resume WORK
  3. 超时 (60s) → auto-shutdown

Identity re-injection:
  上下文被 compact 压缩后 messages ≤ 3 条时，
  插入身份提醒块防止 Agent 忘记自己是谁。
"""

import json
import threading
from pathlib import Path

POLL_INTERVAL = 5   # 空闲轮询间隔（秒）
IDLE_TIMEOUT = 60   # 空闲超时（秒），超时后自动 shutdown

_claim_lock = threading.Lock()


def scan_unclaimed_tasks(tasks_dir: Path) -> list[dict]:
    """扫描 .tasks/ 目录，返回所有可认领的任务。"""
    tasks_dir.mkdir(exist_ok=True)
    unclaimed = []
    for f in sorted(tasks_dir.glob("task_*.json")):
        task = json.loads(f.read_text(encoding="utf-8"))
        if (task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")):
            unclaimed.append(task)
    return unclaimed


def claim_task(task_id: int, owner: str, tasks_dir: Path) -> str:
    """原子认领一个任务（加锁 + 二次校验）。"""
    with _claim_lock:
        path = tasks_dir / f"task_{task_id}.json"
        if not path.exists():
            return f"Error: Task {task_id} not found"
        task = json.loads(path.read_text(encoding="utf-8"))
        if task.get("owner"):
            return f"Error: Task {task_id} already claimed by {task['owner']}"
        if task.get("status") != "pending":
            return f"Error: Task {task_id} status is '{task['status']}'"
        if task.get("blockedBy"):
            return f"Error: Task {task_id} is blocked"
        task["owner"] = owner
        task["status"] = "in_progress"
        path.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Claimed task #{task_id} for {owner}"


def make_identity_block(name: str, role: str, team_name: str) -> dict:
    """生成身份提醒块——用于 compact 后重新告知 Agent 身份。"""
    return {
        "role": "user",
        "content": (
            f"<identity>You are '{name}', role: {role}, "
            f"team: {team_name}. Continue your work.</identity>"
        ),
    }
