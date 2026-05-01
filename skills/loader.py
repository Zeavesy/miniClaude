"""
SkillLoader —— 按需加载的领域知识注入系统。

两层注入策略:
    Layer 1（低成本）: 技能名 + 简短描述注入 system prompt（~100 token/skill）
    Layer 2（按需）:   LLM 调用 load_skill(name) → 完整 SKILL.md body 返回

    这样 system prompt 不会臃肿，但 LLM 在需要时可以获取完整的领域指导。

Skills 目录结构:
    skills/
      agent-builder/
        SKILL.md    ← YAML frontmatter (name, description, tags) + Markdown body
      code-review/
        SKILL.md
      ...

YAML frontmatter 格式:
    ---
    name: agent-builder
    description: Design and build AI agents for any domain.
    tags: agent, builder
    ---
    # Agent Builder
    (Markdown body here...)
    ---  (第二个 --- 结束 frontmatter)
"""

import re
from pathlib import Path

import yaml


class SkillLoader:
    def __init__(self, skills_dir: Path):
        """
        skills_dir: skills/ 目录路径。
        目录不存在时 skills 为空，不会报错。
        """
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, dict] = {}
        self._load_all()

    # ═══════════════════════════════════════════════════════════
    # 扫描与解析
    # ═══════════════════════════════════════════════════════════

    def _load_all(self):
        """递归扫描 skills_dir 下所有 SKILL.md 文件，解析 frontmatter + body。"""
        if not self.skills_dir.exists():
            return
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            text = f.read_text(encoding="utf-8")
            meta, body = self._parse_frontmatter(text)
            # 优先使用 frontmatter 中的 name，否则用所在目录名
            name = meta.get("name", f.parent.name)
            self.skills[name] = {
                "meta": meta,
                "body": body,
                "path": str(f),
            }

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        """
        解析 --- 分隔的 YAML frontmatter。

        输入:
            ---
            name: pdf
            description: Process PDF files...
            ---
            # Full instructions...

        返回: (meta_dict, body_str)
        """
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()

    # ═══════════════════════════════════════════════════════════
    # Layer 1: 名称列表注入 system prompt（低成本）
    # ═══════════════════════════════════════════════════════════

    def get_descriptions(self) -> str:
        """
        返回技能名称和描述列表，供 system prompt 使用。

        输出示例:
            - agent-builder: Design and build AI agents for any domain.
            - code-reviewer: Perform thorough code reviews...
        """
        if not self.skills:
            return "(无可用的技能)"
        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "无描述")
            tags = skill["meta"].get("tags", "")
            line = f"  - {name}: {desc}"
            if tags:
                line += f" [tags: {tags}]"
            lines.append(line)
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # Layer 2: 完整内容返回（按需，LLM 调用 load_skill 时触发）
    # ═══════════════════════════════════════════════════════════

    def get_content(self, name: str) -> str:
        """
        返回指定技能的完整 SKILL.md body。

        如果 LLM 传入的技能名不存在，返回可用技能列表作为提示。
        """
        skill = self.skills.get(name)
        if not skill:
            available = ", ".join(self.skills.keys())
            return f"未知技能 '{name}'。可用技能: {available}"
        return f"<skill name=\"{name}\">\n{skill['body']}\n</skill>"

    @property
    def names(self) -> list[str]:
        return list(self.skills.keys())
