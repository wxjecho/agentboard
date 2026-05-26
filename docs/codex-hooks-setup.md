# Codex Hooks 接入

## 目标

使用 Codex 官方 hooks，把真实的长期交互会话持续上报到 AgentBoard。

当前适配脚本：

- [runner/codex_hook_adapter.py](../runner/codex_hook_adapter.py)

当前项目级 hook 配置：

- [.codex/hooks.json](../.codex/hooks.json)

如果你希望在任意目录启动 `codex` 都自动进入 AgentBoard，还可以额外配置全局 hook：

- `~/.codex/hooks.json`

它会把以下 Codex hook 事件映射到 AgentBoard：

- `SessionStart` -> `agent_started` 和 `running`
- `UserPromptSubmit` -> 更新任务摘要、记录用户 prompt、状态切回 `running`
- `PreToolUse` -> `command_started` 或 `state_changed(editing)`
- `PostToolUse` -> `command_finished`、文件创建/修改事件
- `PermissionRequest` -> `waiting_input`
- `Stop` -> `idle`

这里最关键的语义是：

- `Stop` 不是会话结束
- 对长期交互来说，它表示这一轮回答已经结束，Codex 正在等待下一次用户输入
- 所以适配器不会把 `Stop` 映射成 `agent_finished`

## 使用方式

先启动 AgentBoard 后端和前端：

```bash
cd /path/to/agentboard/backend
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd /path/to/agentboard/frontend
npm run dev -- --host 0.0.0.0 --port 4173
```

然后在 `agentboard` 仓库内直接启动 Codex 交互会话：

```bash
cd /path/to/agentboard
codex
```

或者：

```bash
cd /path/to/agentboard
codex "请阅读 README 并总结项目结构"
```

只要你的当前工作目录是这个仓库，Codex 就会自动加载项目级 `.codex/hooks.json`，把会话持续上报到 AgentBoard。

## 全局接入

如果你希望在任何目录启动 `codex` 都自动上报，可以在 `~/.codex/hooks.json` 中写一份全局 hook 配置，并把命令指向 AgentBoard 里的绝对脚本路径。

这种方式和项目级 hook 的区别是：

- 项目级 hook：只在当前仓库内生效
- 全局 hook：在任何目录启动 `codex` 都生效

全局 hook 的 `command` 不能再依赖当前项目的相对路径，必须写成绝对路径，例如：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"/path/to/agentboard/runner/codex_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ]
  }
}
```

## 行为说明

- 脚本通过 `session_id` 在系统临时目录中的 `agentboard_codex_sessions.json` 中维护会话映射
- `agent_id` 会稳定映射为 `codex-<session_id前缀>`，便于同一长期会话持续更新
- `task` 会优先使用最近一次用户 prompt 的摘要
- `Bash` 工具会记录命令开始/结束
- `Edit`、`Write`、`MultiEdit`、`NotebookEdit` 会记录文件创建/修改
- `PermissionRequest` 会映射为 `waiting_input`
- 一轮回答结束时，`Stop` 会把状态切到 `idle`，表示“会话还活着，但正在等你下一句”

## Hook 信任

如果 Codex 第一次提示你信任项目 hook，允许一次即可。

你也可以在仓库里执行：

```bash
codex --dangerously-bypass-hook-trust
```

这个参数只建议用于你已经确认 hook 脚本可信的本地项目。

## 本地验证

先用 dry-run 验证一个 `SessionStart`：

```bash
echo '{
  "hook_event_name": "SessionStart",
  "session_id": "demo-session",
  "cwd": "/path/to/agentboard",
  "source": "startup",
  "model": "gpt-5.4"
}' | python3 runner/codex_hook_adapter.py --dry-run
```

再验证一轮结束时的 `Stop`：

```bash
echo '{
  "hook_event_name": "Stop",
  "session_id": "demo-session",
  "cwd": "/path/to/agentboard",
  "last_assistant_message": "README 已阅读完毕。"
}' | python3 runner/codex_hook_adapter.py --dry-run
```
