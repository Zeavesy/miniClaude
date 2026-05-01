"""工具模块：文件读写与编辑。"""
from tools.bash import safe_path


def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... (还有 {len(lines) - limit} 行)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"写入 {len(content)} 字节到 {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        c = fp.read_text(encoding="utf-8")
        if old_text not in c:
            return f"Error: 在 {path} 中找不到目标文本"
        fp.write_text(c.replace(old_text, new_text, 1), encoding="utf-8")
        return f"已编辑 {path}"
    except Exception as e:
        return f"Error: {e}"
