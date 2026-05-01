"""
ToolRegistry 类 —— 纯数据结构，不含任何具体工具注册。
被 core/toolbox.py 和 subagent/runner.py 共用，避免循环导入。
"""
import time


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
