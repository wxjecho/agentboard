# Runner

`runner` 目录用于承载 AgentBoard 的本地采集器、mock runner，以及后续面向真实 Agent 的 Hook 和 CLI 适配器。

如果你想直接看安装和接入步骤，优先阅读：

- [docs/install-and-cli-guide.md](/Users/wuxinji/code/agentboard/docs/install-and-cli-guide.md)

## 当前实现

当前已经提供一个零依赖的 mock runner：

- 向后端注册多个模拟 Agent
- 按统一协议持续上报日志、命令、文件修改、等待输入、完成或失败事件
- 可用于本地联调后端 API 和前端实时面板

同时已经提供第一版真实 `Codex CLI` runner：

- 真实启动 `codex exec`
- 注册 Agent 会话并上报生命周期
- 持续上报 stdout / stderr 日志
- 定时发送 heartbeat
- 在结束时上报退出状态与运行时长
- 当检测到重连 / 超时特征时，自动把状态切到 `blocked`
- 自动轮询工作目录并上报 `file_created / file_modified / file_deleted`

同时已经提供通用 `generic_cli_runner`：

- 用同一套 runner 机制接入非 Codex CLI Agent
- 适合 `Gemini CLI`、`cc`、`OpenCode` 以及其他命令行 Agent
- 同样支持生命周期、日志、heartbeat、blocked 检测和文件监听

同时已经提供 `Claude Code` Hook 适配器：

- 基于 Claude Code 官方 Hooks
- 把 `SessionStart`、`PreToolUse`、`PostToolUse`、`Notification`、`Stop` 等事件映射到 AgentBoard
- 适合真实 Claude Code 会话接入

## 启动方式

在仓库根目录执行：

```bash
python3 runner/mock_runner.py --backend http://127.0.0.1:8000 --agents 3
```

如果你想稳定触发“完成 / 等待输入 / 失败”这几类提醒，用这个：

```bash
python3 runner/mock_runner.py --backend http://127.0.0.1:8000 --agents 3 --scenario attention
```

如果只想看将要发送的事件，不实际请求后端：

```bash
python3 runner/mock_runner.py --dry-run
```

## 真实 Codex Runner

在仓库根目录执行：

```bash
python3 runner/codex_runner.py \
  --backend http://127.0.0.1:8000 \
  --project agentboard \
  --task "验证真实 Codex 接入" \
  --prompt "请先阅读 README，然后总结当前项目结构" \
  --print-command
```

如果你只想先验证上报格式，可以加：

```bash
--dry-run
```

## 通用 CLI Runner

如果你要接入其他 CLI Agent，可以执行：

```bash
python3 runner/generic_cli_runner.py \
  --backend http://127.0.0.1:8000 \
  --agent-type gemini-cli \
  --project agentboard \
  --task "验证 Gemini CLI 接入" \
  --print-command \
  -- \
  gemini "请总结当前项目结构"
```

只想预览命令而不执行：

```bash
python3 runner/generic_cli_runner.py \
  --agent-type cc \
  --task "预览通用 CLI 接入" \
  --print-command \
  --preview-only \
  -- \
  cc "hello"
```

## Claude Code Hook Adapter

适配脚本位于：

```bash
python3 runner/claude_hook_adapter.py --backend http://127.0.0.1:8000
```

完整接入说明见：

- [docs/claude-hooks-setup.md](/Users/wuxinji/code/agentboard/docs/claude-hooks-setup.md)

## 主要参数

- `--backend`：后端地址，默认 `http://127.0.0.1:8000`
- `--agents`：模拟 Agent 数量
- `--project`：统一项目名，默认 `agentboard`
- `--interval`：事件间隔秒数，默认 `0.6`
- `--scenario`：事件场景，`standard` 为随机流，`attention` 为固定提醒流
- `--dry-run`：只打印事件，不发请求

真实 Codex runner 常用参数：

- `--task`：显示在面板里的任务标题
- `--prompt`：传给 `codex exec` 的真实提示词
- `--cwd`：Codex 工作目录
- `--model`：可选，指定 Codex 模型
- `--profile`：可选，指定 Codex profile
- `--sandbox`：转发给 `codex exec` 的沙箱模式
- `--ask-for-approval`：转发给 `codex exec` 的审批策略
- `--heartbeat-interval`：心跳间隔
- `--watch-interval`：文件轮询间隔
- `--print-command`：打印最终生成的 Codex 命令

通用 CLI runner 常用参数：

- `--agent-type`：Agent 类型标签，例如 `gemini-cli`、`cc`、`opencode`
- `--task`：显示在面板里的任务标题
- `--cwd`：CLI 工作目录
- `--heartbeat-interval`：心跳间隔
- `--watch-interval`：文件轮询间隔
- `--print-command`：打印最终生成的 CLI 命令
- `--preview-only`：只预览命令，不真正执行

当前 `blocked` 检测规则：

- 日志中出现 `Reconnecting...`
- 或出现 `stream disconnected - retrying sampling request`
- 或出现 `timeout waiting for child process to exit`

命中后会向后端发送 `state_changed -> blocked`；如果后续恢复了正常 stdout 输出，再切回 `executing`。

当前文件监听说明：

- 使用零依赖轮询 watcher
- 默认忽略 `.git`、`node_modules`、`dist`、`.venv`、`__pycache__` 等目录
- 当工作目录内文件发生创建、修改、删除时，会自动上报到 AgentBoard

## 后续方向

- 增加通用 CLI Runner 入口
- 增加 Claude Code Hook 上报适配
- 增加 workspace watcher
