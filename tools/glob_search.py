"""工具模块：Glob 文件模式匹配。"""
from tools.bash import safe_path, WORKDIR


def run_glob(pattern: str, path: str = ".") -> str:
    try:
        base = safe_path(path)
        matches = []
        for f in base.rglob(pattern):
            if f.is_file():
                matches.append(str(f.resolve().relative_to(WORKDIR)))
        matches.sort()
        if not matches:
            return f"未匹配到: {pattern}"
        return "\n".join(matches[:200])
    except Exception as e:
        return f"Error: {e}"
