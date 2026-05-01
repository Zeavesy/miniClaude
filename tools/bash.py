"""工具模块：Shell 命令执行。"""
import subprocess
from pathlib import Path

WORKDIR = Path.cwd()


def safe_path(p: str) -> Path:
    """防止路径逃逸，确保所有文件操作都在 WORKDIR 内。"""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"路径逃逸被拦截: {p}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: 危险命令被拦截"
    try:
        r = subprocess.run(
            command, shell=True, cwd=WORKDIR,
            capture_output=True, text=True, timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(无输出)"
    except subprocess.TimeoutExpired:
        return "Error: 超时 (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"
