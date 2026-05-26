# 真实 Agent 接入总说明

这份文档把 AgentBoard 当前支持的真实接入方式整理到一起，方便你快速判断：

- 你现在该用哪种方案
- 哪些方案适合长期交互
- 哪些方案适合一次性任务
- Claude 和 Codex 的差异在哪里

## 总览

AgentBoard 目前支持三类真实接入：

1. `Claude Code Hooks`
2. `Codex Hooks`
3. `CLI Runner`

推荐优先级：

- 如果目标是长期交互，优先用 `Hooks`
- 如果目标是一次性任务包装，或者某个 CLI 没有原生 hook，再用 `Runner`

## 方案对比

| 方案 | 适用对象 | 会话类型 | 触发方式 | 推荐场景 |
|---|---|---|---|---|
| Claude Hooks | Claude Code | 长期交互 | `.claude/settings.json` | 真实 Claude 会话监控 |
| Codex Hooks | Codex CLI | 长期交互 | `.codex/hooks.json` 或 `~/.codex/hooks.json` | 真实 Codex 会话监控 |
| Codex Runner | `codex exec` | 一次性任务 | `python3 runner/codex_runner.py ...` | 包装单次 Codex 任务 |
| Generic CLI Runner | `gemini` / `cc` / `opencode` 等 | 一次性任务 | `python3 runner/generic_cli_runner.py ... -- your-command` | 其他 CLI Agent 接入 |

## Claude Code

Claude 更适合走官方 Hooks，而不是外层进程包装。

当前实现：

- 适配器：[claude_hook_adapter.py](../runner/claude_hook_adapter.py)
- 说明文档：[claude-hooks-setup.md](claude-hooks-setup.md)

接入方式：

- 在项目里配置 `.claude/settings.json`
- 把 Hook 事件转成 AgentBoard 事件

当前主要映射：

- `SessionStart` -> `agent_started`
- `PreToolUse` -> `command_started` 或 `editing`
- `PostToolUse` -> `command_finished`、文件修改
- `Notification` -> `waiting_input`
- `Stop` -> `agent_finished`

适合场景：

- 你平时就长期使用 Claude Code
- 你希望每轮工具调用、文件修改、等待输入都能进面板

## Codex

Codex 现在有两种接入方式，但用途不同。

### 1. Codex Hooks

这是长期交互方案，也是目前对真实 Codex 最推荐的方式。

当前实现：

- 适配器：[codex_hook_adapter.py](../runner/codex_hook_adapter.py)
- 说明文档：[codex-hooks-setup.md](codex-hooks-setup.md)

接入位置：

- 项目级：`.codex/hooks.json`
- 全局：`~/.codex/hooks.json`

当前主要映射：

- `SessionStart` -> `agent_started` + `running`
- `UserPromptSubmit` -> 更新任务摘要 + `running`
- `PreToolUse` -> `command_started` 或 `editing`
- `PostToolUse` -> `command_finished`、文件修改
- `PermissionRequest` -> `waiting_input`
- `Stop` -> `idle`

和 Claude 最大的区别：

- Codex 的 `Stop` 更适合理解为“一轮结束，等待下一句”
- 所以这里不会把 `Stop` 映射成 `agent_finished`
- 这样更符合长期交互会话的实际语义

适合场景：

- 你希望直接运行 `codex`
- 你希望在同一个长期会话里持续追问
- 你希望 AgentBoard 跟踪整段 Codex 会话，而不是只记录一次性任务

### 2. Codex Runner

这是一次性任务包装方案，不是长期交互方案。

当前实现：

- 脚本：[codex_runner.py](../runner/codex_runner.py)

它本质上包装的是：

```bash
codex exec ...
```

适合场景：

- 你就是想发起一条单次 Codex 任务
- 你想把这次任务完整记录到 AgentBoard
- 你不关心长期会话连续性

不适合场景：

- 你希望直接进入 Codex TUI 并长期交互

## 其他命令行 Agent

如果某个 Agent 没有官方 hook，或者你只需要先快速接进面板，可以用通用 runner。

当前实现：

- 脚本：[generic_cli_runner.py](../runner/generic_cli_runner.py)

适用对象：

- `gemini`
- `cc`
- `opencode`
- 你自己的 CLI Agent

这类方案的特点是：

- 启动快
- 接入门槛低
- 但本质还是外层包装，天然更偏向“一次性任务”

## 怎么选

如果你只看一个结论，可以按这个选：

- 用 Claude 长期交互：选 `Claude Hooks`
- 用 Codex 长期交互：选 `Codex Hooks`
- 用 Codex 单次执行：选 `Codex Runner`
- 用其他 CLI 单次执行：选 `Generic CLI Runner`

## 推荐实践

如果你自己长期本机使用 AgentBoard，推荐这样配置：

1. 后端常驻在 `127.0.0.1:8000`
2. 前端常驻在 `127.0.0.1:4173`
3. Claude 走 hooks
4. Codex 走 hooks
5. 其他 CLI 先走 generic runner

这样你的主力长期会话都有持续状态，面板里的语义也更自然。

## 相关文档

- [claude-hooks-setup.md](claude-hooks-setup.md)
- [codex-hooks-setup.md](codex-hooks-setup.md)
- [install-and-cli-guide.md](install-and-cli-guide.md)
- [runner/README.md](../runner/README.md)
