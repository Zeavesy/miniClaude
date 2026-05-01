# Context Compact 对比测试：连续阅读 12 个源文件

> 模型: deepseek-chat
> 阈值: 20000 tokens (auto_compact)
> 文件: 12 files from learn-claude-code/agents/
> 生成: 2026-05-01 12:04:51

## 一、汇总对比

| 指标 | Without CompactManager | With CompactManager |
|------|----------------------|---------------------|
| 总回合数 | 53 | 10 |
| Token 消耗 (估算) | 53477 | 1779 |
| 阅读阶段耗时 (s) | 140.7 | 99.6 |
| 总耗时 (s) | 145.0 | 104.1 |
| 压缩触发次数 | 0 | 1 |

## 二、问答准确率对比

### Without CompactManager

| 问题 | 来源文件 | 类型 | 回答 (截断) | 关键词命中 |
|------|---------|------|------------|-----------|
| Q1_early | s02_tool_use.py | 早期 | In `s02_tool_use.py`, the `TOOL_HANDLERS` dictionary maps four tool names — `"bash"`, `"read_file"`, `"write_file"`, and | 4/4 (bash, read_file, write_file, edit_file) |
| Q2_early | s03_todo_write.py | 早期 | In `s03_todo_write.py`, the nag reminder mechanism injects a `<reminder>Update your todos.</reminder>` text message alon | 2/3 (3, reminder) |
| Q3_late | s09_agent_teams.py | 后期 | In `s09_agent_teams.py`, teammates communicate by sending messages via the `MessageBus` which appends JSON lines to per- | 3/3 (JSONL, inbox, MessageBus) |

### With CompactManager

| 问题 | 来源文件 | 类型 | 回答 (截断) | 关键词命中 |
|------|---------|------|------------|-----------|
| Q1_early | s02_tool_use.py | 早期 | From my recollection of the files read earlier in this conversation, the file `s02_tool_use.py` was **not** among the fi | 0/4 () |
| Q2_early | s03_todo_write.py | 早期 | Based on my recollection, `s03_todo_write.py` was the first file I read in this conversation. The nag reminder mechanism | 3/3 (3, reminder, TodoWrite) |
| Q3_late | s09_agent_teams.py | 后期 | Based on my recollection, in `s09_agent_teams.py`, teammates communicate through a shared filesystem — each agent writes | 0/3 () |

## 三、分析

- **Token 差异**: With Compact 消耗 1779 vs Without 53477 (-97%)
- **回合差异**: With Compact 10 轮 vs Without 53 轮 (-81%)
- **压缩触发**: With Compact 触发了 1 次压缩

- **Without CompactManager** 早期文件回忆: 6/7 关键词命中, 后期文件回忆: 3/3
- **With CompactManager** 早期文件回忆: 3/7 关键词命中, 后期文件回忆: 0/3

## 四、完整回答

### Without CompactManager

**Q1_early** (s02_tool_use.py):
> In `s02_tool_use.py`, the `TOOL_HANDLERS` dictionary maps four tool names — `"bash"`, `"read_file"`, `"write_file"`, and `"edit_file"` — to their respective handler functions (`run_bash`, `run_read`, `run_write`, `run_edit`).

**Q2_early** (s03_todo_write.py):
> In `s03_todo_write.py`, the nag reminder mechanism injects a `<reminder>Update your todos.</reminder>` text message alongside tool results when 3 rounds pass without the model using the `todo` tool (`rounds_since_todo >= 3`).

**Q3_late** (s09_agent_teams.py):
> In `s09_agent_teams.py`, teammates communicate by sending messages via the `MessageBus` which appends JSON lines to per-teammate JSONL inbox files stored in `.team/inbox/`, and recipients read and drain their inbox by reading and clearing that file.

### With CompactManager

**Q1_early** (s02_tool_use.py):
> From my recollection of the files read earlier in this conversation, the file `s02_tool_use.py` was **not** among the files I read — I read s03 through s11 from the `learn-claude-code-main/agents/` directory, starting from s03. I do not have the content of `s02_tool_use.py` in context.

If you'd lik

**Q2_early** (s03_todo_write.py):
> Based on my recollection, `s03_todo_write.py` was the first file I read in this conversation. The nag reminder mechanism triggers after **3 rounds** without using the `TodoWrite` tool — it prints a reminder message urging the agent to write a todo list entry.

**Q3_late** (s09_agent_teams.py):
> Based on my recollection, in `s09_agent_teams.py`, teammates communicate through a shared filesystem — each agent writes messages to and reads messages from a "scratchpad" directory using `TodoWrite` and `TodoRead` tools, with the underlying storage being plain text files on disk.
