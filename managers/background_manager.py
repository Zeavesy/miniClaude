"""
BackgroundManager — 后台线程执行耗时命令（不阻塞 Agent Loop）。

"""

import subprocess
import threading
import time
import uuid
from pathlib import Path


class BackgroundManager:
    def __init__(self, workdir: Path = None):
        """
        workdir: 线程中 subprocess.run 的工作目录。
        不传则取构造时的 Path.cwd()。
        """
        self.workdir = workdir or Path.cwd()

        # self.tasks: {task_id: {status, command, result}}
        # 主线程写入（run 时初始化），工作线程写入（_execute 完成时更新结果）
        self.tasks: dict[str, dict] = {}

        # _notifications: 已完成任务的"邮件队列"
        # 工作线程生产（_execute 末尾 push），主线程消费（drain_notifications）
        # 用 _lock 保护并发读写
        self._notifications: list[dict] = []
        self._lock = threading.Lock()

    def run(self, command: str, timeout: int = 300) -> str:
        """
        启动一个后台任务。

        1. 生成 8 位短 task_id (uuid4 前 8 字符)
        2. 在 self.tasks 中注册为 "running"
        3. 启动 daemon 线程（主进程退出时自动回收）
        4. 立即返回确认信息给 LLM

        返回: "后台任务 a1b2c3d4 已启动: npm install ..."
        """
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {
            "status": "running",
            "command": command,
            "result": None,
        }
        t = threading.Thread(
            target=self._execute,
            args=(task_id, command, timeout),
            daemon=True,   # 主进程退出时不需要等后台线程跑完
        )
        t.start()
        return f"后台任务 {task_id} 已启动: {command[:80]}"

    def _execute(self, task_id: str, command: str, timeout: int):
        """
        线程入口（运行在后台 daemon 线程中）。

        1. subprocess.run 执行命令（阻塞当前线程，不阻塞主线程）
        2. 更新 self.tasks[task_id] 的状态和结果
        3. 将完成通知推入 _notifications 队列（加锁保护）
        """
        try:
            r = subprocess.run(
                command, shell=True, cwd=self.workdir,
                capture_output=True, text=True, timeout=timeout,
            )
            output = (r.stdout + r.stderr).strip()[:50000] or "(无输出)"
            status = "completed"
        except subprocess.TimeoutExpired:
            output = f"Error: 超时 ({timeout}s)"
            status = "timeout"
        except Exception as e:
            output = f"Error: {e}"
            status = "error"

        # 更新任务状态
        self.tasks[task_id].update({"status": status, "result": output})

        # 推入通知队列——agent_loop 会在下一轮 drain 走
        with self._lock:
            self._notifications.append({
                "task_id": task_id,
                "status": status,
                "result": output[:500],    # 通知只保留前 500 字符，完整结果在 self.tasks 中
                "ts": time.time(),
            })

    def check(self, task_id: str = None) -> str:
        """
        查询后台任务状态。

        传入 task_id: 查询单个任务详情（包括结果文本）
        不传 task_id: 列出所有任务的概览
        """
        if task_id:
            t = self.tasks.get(task_id)
            if not t:
                return f"未知任务: {task_id}"
            # 如果还在运行，result 为 None，显示 "(运行中)"
            return f"[{t['status']}] {t['command'][:60]}\n{t.get('result') or '(运行中)'}"

        if not self.tasks:
            return "无后台任务。"
        lines = []
        for tid, t in self.tasks.items():
            lines.append(f"{tid}: [{t['status']}] {t['command'][:60]}")
        return "\n".join(lines)

    def drain_notifications(self) -> list[dict]:
        """
        取出并清空所有待处理的完成通知。

        被 agent_loop 在每轮 LLM 调用前调用:
          - 返回列表中每个 dict 含 task_id、status、result 前 500 字符
          - 清空内部通知队列
          - 加锁保证线程安全

        返回空列表意味着: 没有后台任务刚完成。
        """
        with self._lock:
            notifs = list(self._notifications)
            self._notifications.clear()
        return notifs
