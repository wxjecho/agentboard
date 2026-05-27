# Claude Code Hooks 接入

## 目标

使用 Claude Code 官方 Hooks，把真实会话事件接入 AgentBoard。

当前适配脚本：

- [runner/claude_hook_adapter.py](../runner/claude_hook_adapter.py)

也可以直接用一键安装：

```bash
python3 runner/claude_hook_adapter.py --install --backend http://127.0.0.1:8000
```

它会把以下 Hook 事件映射到 AgentBoard：

- `SessionStart` -> `agent_started`
- `UserPromptSubmit` -> 会话任务摘要更新与日志记录
- `PreToolUse` -> `command_started` 或 `state_changed(editing)`
- `PostToolUse` -> `command_finished`、文件修改事件
- `PostToolUseFailure` -> 失败日志和 `state_changed(blocked)`
- `Notification` -> `waiting_input` 或普通日志
- `Stop` -> `agent_finished`
- `SessionEnd` -> 清理本地会话状态

## 参考

本接入基于 Claude Code 官方文档：

- Hooks reference: https://code.claude.com/docs/en/hooks
- Hooks guide: https://code.claude.com/docs/en/hooks-guide

关键点：

- `SessionStart` 会提供 `source` 和 `model`
- `PreToolUse` / `PostToolUse` 会提供 `tool_name`、`tool_input`、`tool_response`
- `Notification` 会提供 `message`、可选 `title` 和 `notification_type`
- `Stop` 会提供 `last_assistant_message`

## 示例配置

把下面内容加入项目的 `.claude/settings.json`：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "clear|resume|logout|prompt_input_exit|other",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/runner/claude_hook_adapter.py\" --backend http://127.0.0.1:8000"
          }
        ]
      }
    ]
  }
}
```

如果你不想手动编辑，可以在项目根目录执行：

```bash
python3 runner/claude_hook_adapter.py --install --backend http://127.0.0.1:8000
```

默认会写入当前目录下的 `.claude/settings.json`。如果你想指定路径，可以追加：

```bash
python3 runner/claude_hook_adapter.py --install \
  --backend http://127.0.0.1:8000 \
  --settings-path /path/to/project/.claude/settings.json
```

## 行为说明

- 脚本通过 `session_id` 在 `tempfile.gettempdir()` 对应的系统临时目录中维护 `agentboard_claude_sessions.json`
- `task` 会优先取最近一次 `UserPromptSubmit` 的 prompt 摘要
- 对 `Bash` 工具会记录命令开始/结束
- 对 `Edit`、`Write`、`MultiEdit`、`NotebookEdit` 会记录文件创建/修改
- 对 `permission_prompt`、`idle_prompt`、`elicitation_dialog` 这类通知会映射为 `waiting_input`

## 本地验证

可以先用 dry-run 测试一个样例 payload：

```bash
echo '{
  "session_id": "demo-session",
  "cwd": "/path/to/agentboard",
  "hook_event_name": "Notification",
  "message": "Claude is waiting for your approval",
  "notification_type": "permission_prompt"
}' | python3 runner/claude_hook_adapter.py --dry-run
```
