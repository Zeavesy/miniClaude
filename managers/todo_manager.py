"""
TodoManager — 当前会话内的短期任务进度跟踪（内存中，进程退出即消失）。

"""


class TodoManager:
    def __init__(self):
        # self.items 结构: [{"content": str, "status": str, "activeForm": str}, ...]
        self.items: list[dict] = []

    def update(self, items: list[dict]) -> str:
        """
        接收 LLM 传来的整份任务列表（全量替换，不是增量追加）。

        每次 TodoWrite 调用都会传进来完整列表——
        这意味着 LLM 负责维护"当前所有任务的快照"，
        TodoManager 只做校验 + 存储 + 渲染，不做合并。

        返回: render() 的格式化字符串，作为 tool_result 回给 LLM。
        """
        if len(items) > 20:
            raise ValueError("最多 20 个待办项")

        validated = []
        in_progress_count = 0

        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active_form = str(item.get("activeForm", "")).strip()

            # 校验 1: 每项必须有内容描述
            if not content:
                raise ValueError(f"第 {i + 1} 项: content 不能为空")

            # 校验 2: 状态必须是三态之一
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"'{content}': 无效状态 '{status}'")

            # 校验 3: in_progress 项应提供 activeForm，但不强制
            if status == "in_progress":
                in_progress_count += 1
                if not active_form:
                    # 部分模型（如 DeepSeek）不完全遵守 activeForm 必填约束
                    # 这里用 content 做 fallback，保证系统不会因格式问题中断
                    active_form = content

            validated.append({
                "content": content,
                "status": status,
                "activeForm": active_form,
            })

        # 校验 4: 同时只有 1 个 in_progress——强制单线程聚焦
        if in_progress_count > 1:
            raise ValueError("同时只能有 1 个 in_progress 项")

        self.items = validated
        return self.render()

    def render(self) -> str:
        """
        把当前任务列表格式化为人类可读的 Markdown 风格文本。

        输出示例:
            [ ] 创建目录结构
            [>] 编写核心代码 ← write_file
            [x] 安装依赖

            (1/3 完成)
        """
        if not self.items:
            return "暂无待办项。"

        lines = []
        for item in self.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(item["status"], "[?]")

            # in_progress 项后面标注当前正在用的工具，方便观察
            suffix = f" ← {item['activeForm']}" if item["status"] == "in_progress" else ""
            lines.append(f"{marker} {item['content']}{suffix}")

        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} 完成)")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        """
        是否有未完成项。

        被 agent_loop 的 nag reminder 机制调用:
          - 如果有未完成任务 且 连续 3 轮没用 TodoWrite
          - → 在下一轮 LLM 调用前注入提醒
        """
        return any(t["status"] != "completed" for t in self.items)
