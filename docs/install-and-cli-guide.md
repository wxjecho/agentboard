# 安装部署与 CLI 接入指南

这份文档面向两个目标：

- 在你自己的机器上把 AgentBoard 跑起来
- 把你常用的 Agent CLI 接进 AgentBoard 面板

## 1. 环境要求

- Python `3.9+`
- Node.js `18+`
- `npm`
- 可选：
  - `codex`
  - `claude`
  - 其他命令行 Agent，例如 `gemini`、`cc`、`opencode`

建议先确认这些命令可用：

```bash
python3 --version
node --version
npm --version
```

如果你要接真实 `Codex`，再确认：

```bash
codex --help
```

## 2. 安装项目

克隆仓库：

```bash
git clone https://github.com/wxjecho/agentboard.git
cd agentboard
```

安装后端依赖：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

安装前端依赖：

```bash
cd frontend
npm install
cd ..
```

## 3. 启动方式

### 方式 A：本地开发

启动后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

启动前端：

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 4173
```

访问地址：

- 前端：`http://127.0.0.1:4173`
- 后端：`http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/health`

### 方式 B：本机常驻

如果你只是自己长期用，不一定要上 Docker 或云服务，直接本机常驻就够了。

后端：

```bash
cd /path/to/agentboard/backend
source .venv/bin/activate
nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/agentboard-backend.log 2>&1 &
```

前端：

```bash
cd /path/to/agentboard/frontend
nohup npm run dev -- --host 127.0.0.1 --port 4173 >/tmp/agentboard-frontend.log 2>&1 &
```

更稳一点的话，也可以自己放进 `tmux`、`screen` 或 `systemd --user`。

## 4. 先验证面板是否正常

先用 mock 数据验证整条链路：

```bash
cd /path/to/agentboard
python3 runner/mock_runner.py --backend http://127.0.0.1:8000 --agents 3 --scenario attention
```

这个场景会稳定产生：

- 一个等待输入
- 一个任务失败
- 一个任务完成

适合直接观察：

- 总览卡片排序
- 详情时间线
- 页面 toast
- 顶部强提醒
- 提示音和系统通知

## 5. 接入你自己的 CLI

AgentBoard 目前支持三种接入方式。

### 5.1 Codex CLI

如果你本来是这样运行：

```bash
codex exec "请总结当前项目结构"
```

现在改成通过 AgentBoard 包装器启动：

```bash
cd /path/to/agentboard
python3 runner/codex_runner.py \
  --backend http://127.0.0.1:8000 \
  --project my-project \
  --task "总结项目结构" \
  --cwd /path/to/your/project \
  --prompt "请总结当前项目结构"
```

这样会自动接入：

- Agent 注册
- 日志流
- heartbeat
- `blocked` 检测
- 文件修改监听
- 完成 / 失败上报

如果你想看看最终会执行什么命令，但不真的启动 `codex`：

```bash
python3 runner/codex_runner.py \
  --task "预览 Codex 命令" \
  --cwd /path/to/your/project \
  --prompt "请总结当前项目结构" \
  --print-command \
  --preview-only
```

### 5.2 其他命令行 Agent

如果你用的是 `gemini`、`cc`、`opencode`，或者你自己的 Agent CLI，可用通用 runner：

```bash
cd /path/to/agentboard
python3 runner/generic_cli_runner.py \
  --backend http://127.0.0.1:8000 \
  --agent-type gemini-cli \
  --project my-project \
  --task "让 Gemini 总结项目结构" \
  --cwd /path/to/your/project \
  -- \
  gemini "请总结当前项目结构"
```

重点是命令分隔符 `--`：

- 前面是 AgentBoard runner 自己的参数
- 后面才是你真实要执行的 CLI 命令

比如接 `cc`：

```bash
python3 runner/generic_cli_runner.py \
  --backend http://127.0.0.1:8000 \
  --agent-type cc \
  --project my-project \
  --task "让 cc 检查当前目录" \
  --cwd /path/to/your/project \
  -- \
  cc "请检查当前目录结构"
```

### 5.3 Claude Code Hooks

Claude Code 更适合走 Hook，而不是外层进程包装。

接入步骤：

1. 确保 AgentBoard 后端已经运行
2. 按 [claude-hooks-setup.md](/Users/wuxinji/code/agentboard/docs/claude-hooks-setup.md) 配置 `.claude/settings.json`
3. 把 hook 命令指向：

```bash
python3 "/path/to/agentboard/runner/claude_hook_adapter.py" --backend http://127.0.0.1:8000
```

完成后，Claude 的会话开始、工具调用、通知、结束事件就会进入 AgentBoard。

## 6. 推荐的“自己用”方式

如果你平时主要在本机开发，我建议这么用：

1. 常驻启动 AgentBoard 后端
2. 常驻启动 AgentBoard 前端
3. 浏览器固定打开 `http://127.0.0.1:4173`
4. 把常用 CLI 改成 wrapper 命令

例如你可以在 `~/.zshrc` 里加一个别名：

```bash
alias codexb='python3 /path/to/agentboard/runner/codex_runner.py --backend http://127.0.0.1:8000 --project my-project'
```

之后这样用：

```bash
codexb --task "实现登录页" --cwd /path/to/your/project --prompt "请实现一个登录页"
```

如果是通用 CLI，也可以做类似别名：

```bash
alias agent-run='python3 /path/to/agentboard/runner/generic_cli_runner.py --backend http://127.0.0.1:8000 --project my-project'
```

例如：

```bash
agent-run --agent-type cc --task "检查项目" --cwd /path/to/your/project -- cc "请检查当前项目"
```

## 7. 常见问题

### 页面没有数据

先检查：

- 后端是否存活：`curl http://127.0.0.1:8000/health`
- 前端是否打开了正确地址：`http://127.0.0.1:4173`
- 是否真的运行了 mock 或真实 runner

### 看不到通知

通知依赖“页面打开之后的新事件”，建议直接打一轮：

```bash
python3 runner/mock_runner.py --backend http://127.0.0.1:8000 --agents 3 --scenario attention
```

同时建议在页面上：

- 开启系统通知
- 开启提示音

### Codex 没进面板

通常是因为你直接运行了 `codex`，而不是通过：

```bash
python3 runner/codex_runner.py ...
```

只有通过 runner 启动，AgentBoard 才能收到它的注册、日志和状态事件。

### generic CLI 没进面板

通常是因为 `--` 后面的真实命令没有写对。先用：

```bash
python3 runner/generic_cli_runner.py ... --print-command --preview-only -- your-command
```

先确认命令拼装正确，再真实执行。
