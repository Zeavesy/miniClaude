# Context Compact v2: 阈值 40K + 全局理解型问题

> 模型: deepseek-chat
> 阈值: 40000 tokens
> 文件: 12 files × 2 groups = 24 次读取
> 问题: 4 个全局理解型（演进、Manager、哲学、子代理）
> 生成: 2026-05-01 13:05:30

## 一、汇总对比

| 指标 | Without Compact | With Compact | 差异 |
|------|----------------|-------------|------|
| 总回合数 | 33 | 32 | -3% |
| Token 消耗 | 45794 | 23293 | -49% |
| 阅读耗时 (s) | 34.2 | 32.2 | -6% |
| 总耗时 (s) | 49.2 | 45.6 | -7% |
| 压缩触发次数 | 0 | 0 | - |

## 二、阅读阶段 Token 推移对比

> 每个数字代表读完该文件后的 estimate_tokens，粗体为触发 compact 轮次。

- Without Compact 最终: 45794 tokens（全程未压缩，线性增长）
- With Compact 最终: 23293 tokens（压缩后回到低水位）
- Token 节省: 22501 (49%)

## 三、回答质量对比

### Without Compact

**Q1_evolution**:
> The 12 files evolve through four clear phases:
> 
> **Phase 1 (s01–s02): Core Loop & Tools** — s01 establishes the fundamental `while stop_reason == "tool_use"` agent loop, and s02 adds a dispatch map (`TOOL_HANDLERS`) to route multiple tools (bash, read/write/edit files) without changing the loop itself.
> 
> **Phase 2 (s03–s06): Agent Self-Management** — s03 adds a `TodoManager` with nag reminders for the agent to track its own progress; s04 introduces subagents with fresh, isolated message contexts; s05 implements on-demand skill loading via `SKILL.md` files; s06 adds three-layer context compression (micro_compact → auto_compact → manual compact) for infinite sessions.
> 
> **Phase 3 (s07–s09): Persistent State & Parallelism** — s07 moves task tracking to JSON files in `.tasks/` with dependency graphs; s08 adds background threads with a notification queue for non-blocking execution; s09 introduces persistent named teammates with file-based JSONL inboxes, each running in its own thread.
> 
> **Phase 4 (s10–s12): Coordination & Isolation** — s10 adds structured handshake protocols (shutdown and plan approval) using request_id correlation; s11 implements autonomy with idle polling, task board auto-claiming, and identity re-injection after compression; s12 provides directory-level isolation via git worktrees, binding tasks to isolated parallel execution lanes with lifecycle event logging.

**Q2_managers**:
> Five Manager classes appear across the files:
> 
> 1. **`TodoManager`** (s03) — tracks task list state with validation (max 20 items, single in_progress) and renders progress markers, solving the problem of the agent forgetting what to do next.
> 2. **`TaskManager`** (s07) — persists tasks as `.tasks/task_*.json` files with dependency graphs (blockedBy), surviving context compression; s12 extends it with worktree bindings.
> 3. **`BackgroundManager`** (s08) — runs commands in daemon threads with a notification queue drained before each LLM call, solving blocking execution.
> 4. **`TeammateManager`** (s09, s10, s11) — spawns persistent named agents in separate threads with `.team/config.json` tracking, evolving from basic spawn/idle in s09 to shutdown/plan protocols in s10 and autonomous task-board polling with identity re-injection in s11.
> 5. **`WorktreeManager`** (s12) — creates/removes/keeps git worktrees with an `.worktrees/index.json` index and an `EventBus` for lifecycle events, providing directory-level isolation for parallel task execution.
> 
> These Managers compose vertically: `TodoManager` tracks the current task, `TaskManager` persists tasks across sessions, `BackgroundManager` runs non-blocking work, `TeammateManager` distributes work across threads, and `WorktreeManager` isolates risky changes into separate directories — all bound through task IDs and the same filesystem.

**Q3_philosophy**:
> The author's core philosophy is **"the loop didn't change, I just added tools"** — a consistent pattern where the fundamental `while stop_reason == "tool_use"` agent loop (s01) remains untouched while capabilities layer on top through tool definitions and dispatch maps. This is evidenced by repeated comments: s02 says *"The loop didn't change at all. I just added tools,"* s09 says *"these base tools are unchanged from s02"* (repeated verbatim in s10, s11), and s12 also says *"these base tools are unchanged from s02."* The author emphasizes **filesystem-level persistence over in-memory state** (*"State that survives compression — because it's outside the conversation"* from s07, and *"Process isolation gives context isolation for free"* from s04) and **on-demand loading over upfront bloat** (*"Don't put everything in the system prompt. Load on demand"* from s05). The closing insight is that the agent should **find work itself** — s11's key insight says *"The agent finds work without being told"* — achieved through task board polling, idle cycles, and identity re-injection after compression.

**Q4_subagent**:
> The subagent shares the **filesystem** (workspace directory) with the parent agent but gets a **fresh, isolated message context** (`messages=[]`) — the child's conversation history is discarded and only a summary is returned. This isolation is important because it prevents the subagent's noisy exploration history from bloating the parent's context window and protects the parent's "clarity of thought" (as stated in the docstring: *"Context isolation — protecting the model's clarity of thought"*).

### With Compact

**Q1_evolution**:
> Based on the 12 files read, here is how the architecture evolves layer by layer:
> 
> **Phase 1 (s01-s02): Foundation** — s01 establishes the basic agent loop (prompt → LLM → response → loop) while s02 adds tool execution (bash, read/write/edit files) with tool dispatch and `tool_use` response handling, forming the core agent pattern.
> 
> **Phase 2 (s03-s04): Persistence & Decomposition** — s03 introduces structured file writing (todo lists), and s04 adds subagent spawning where the lead agent can delegate work to child agents running in separate threads with their own message history.
> 
> **Phase 3 (s05-s06): State Management** — s05 adds skill loading from external skill files, and s06 implements context compression with identity re-injection to manage conversation window limits.
> 
> **Phase 4 (s07-s08): Task & Background Systems** — s07 introduces a persistent JSON-based task board with CRUD operations and dependency tracking, while s08 adds background task execution with status polling and timeout management.
> 
> **Phase 5 (s09-s10): Multi-Agent Teams** — s09 builds a full team system with JSONL inbox messaging, spawn/kill lifecycle, and s10 adds structured protocols (shutdown FSM and plan approval) using `request_id` correlation for multi-agent coordination.
> 
> **Phase 6 (s11-s12): Autonomy & Isolation** — s11 enables autonomous agents that idle-poll for unclaimed tasks from the board, and s12 adds git worktree-based directory isolation so parallel tasks execute in separate branches/directories without collision.

**Q2_managers**:
> Based on the files read, four Manager classes are introduced:
> 
> 1. **TeammateManager** (s09, enhanced in s10-s11) — manages teammate lifecycle (spawn, status tracking, thread management) using a JSON config file and threading, solving multi-agent coordination.
> 2. **MessageBus** (s09-s11) — handles inter-agent communication via JSONL inbox files per teammate, solving message routing and inbox draining.
> 3. **TaskManager** (s12) — manages a persistent task board (create, update, bind worktree, list) stored as JSON files in `.tasks/`, solving work tracking and dependency management.
> 4. **WorktreeManager** (s12) — manages git worktree lifecycle (create, run commands in, remove, keep) with an index file and event bus, solving parallel execution isolation.
> 
> These Managers work together by layering: **TeammateManager** spawns agents that use **MessageBus** to communicate, while **TaskManager** holds shared work items that agents claim and bind to **WorktreeManager**-created git worktrees for isolated execution, with all lifecycle events tracked through **EventBus** (s12).

**Q3_philosophy**:
> The author's core philosophy is **progressive minimalism with composable state machines**. This is evidenced by the recurring comment pattern across files: `"these base tools are unchanged from s02"` (s07, s08, s09, s10, s11) — showing they deliberately reuse and compose rather than rewrite. The author emphasizes **correlation patterns** with `"Same request_id correlation pattern, two domains"` (s10), **identity re-injection** after compression with `"Continue your work"` (s06, s11), and **self-directed agent behavior** with `"The agent finds work itself"` (s11) and `"Isolate by directory, coordinate by task ID"` (s12). Each file ends with a **key insight** comment (e.g., `"Key insight: 'The agent finds work itself.'"` in s11, `"Key insight: 'Isolate by directory, coordinate by task ID.'"` in s12), crystallizing the single design principle added per layer.

**Q4_subagent**:
> In s04_subagent.py, the subagent shares the workspace directory (WORKDIR) and the Anthropic client configuration, but isolates its own message history, thread execution, and status tracking. This isolation is important so that the subagent operates independently without corrupting the parent agent's conversation state, enabling parallel delegated work with separate context windows.

## 四、分析

- **Token 效率**: With Compact 消耗 23293 vs Without 45794，节省 49%
- **压缩触发**: With Compact 触发 0 次
- **阈值策略**: 40K 阈值让全部 12 个文件在压缩前都被纳入摘要输入，避免 v1 中早期文件信息丢失的问题
- **问题类型影响**: 全局理解型问题对摘要更友好——不需要精确变量名，跨文件模式在摘要中更易保留

- **Q1_evolution**: Without=1394 chars, With=1525 chars
- **Q2_managers**: Without=1394 chars, With=1079 chars
- **Q3_philosophy**: Without=1106 chars, With=868 chars
- **Q4_subagent**: Without=500 chars, With=384 chars