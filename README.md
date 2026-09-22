# miniClaude

一个从零实现的轻量级 AI Coding Agent。它基于 Anthropic API 运行在命令行中，能够读取和修改文件、执行 Shell 命令、管理任务，并通过 Skills、子 Agent 和多 Agent 协作完成更复杂的开发工作。

## 功能

- 流式对话与工具调用
- 文件读取、写入、编辑和 Glob 搜索
- Shell 命令与后台任务执行
- 会话 Todo 和持久化任务管理
- 自动、手动和轻量级上下文压缩
- 按需加载本地 Skills
- 一次性子 Agent 与持久化队友协作
- Git Worktree 任务隔离

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Zeavesy/miniClaude.git
cd miniClaude
```

### 2. 安装依赖

建议使用 Python 3.10 或更高版本。

```bash
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置模型

在项目根目录创建 `.env`：

```env
ANTHROPIC_API_KEY=your_api_key
MODEL_ID=claude-sonnet-4-6

# 可选：自定义 Anthropic 兼容接口地址
# ANTHROPIC_BASE_URL=https://your-api-endpoint
```

### 4. 启动

```bash
python main.py
```

程序会将启动时所在目录作为工作区。为了避免 Agent 修改无关文件，建议在目标 Git 仓库中运行。

## 内置命令

| 命令         | 说明                   |
| ------------ | ---------------------- |
| `/tasks`     | 查看持久化任务         |
| `/skills`    | 查看可用 Skills        |
| `/team`      | 查看 Agent 队友状态    |
| `/compact`   | 手动压缩当前对话上下文 |
| `q` / `exit` | 退出程序               |

## 项目结构

```text
miniClaude/
├── main.py          # 命令行入口
├── core/            # Agent Loop、模型客户端和工具注册
├── tools/           # Shell、文件操作和搜索工具
├── managers/        # Todo、任务和后台任务管理
├── context/         # 上下文压缩
├── skills/          # Skills 加载器及内置技能
├── subagent/        # 一次性子 Agent
├── team/            # 多 Agent 通信、协议和 Worktree 管理
└── test/            # 上下文压缩测试记录
```

## 添加 Skill

在 `skills/<skill-name>/SKILL.md` 中添加带 YAML Front Matter 的 Markdown 文件：

```markdown
---
name: my-skill
description: 这个 Skill 的用途
---

# 使用说明

在这里编写供 Agent 按需加载的指导内容。
```

重启程序后，新 Skill 会自动出现在 `/skills` 列表中。
