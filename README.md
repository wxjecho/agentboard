# AgentBoard

AgentBoard 是一个面向 AI Coding Agent 的本地优先监控平台，用来统一采集和展示多个 Agent 的生命周期、执行日志、命令记录、文件修改和实时状态。

## 项目范围

本仓库以 `AI Agent Monitor Platform.md` 为需求来源，采用 monorepo 结构，当前分为四个部分：

- `backend`：后端 API、数据持久化、WebSocket 实时推送
- `frontend`：实时监控面板
- `runner`：本地采集器、mock runner，以及后续 Hook 适配
- `docs`：开发计划与实现文档

## 第一阶段目标

第一阶段先完成一个本地可运行的 MVP，支持：

- Agent 注册
- 事件上报
- Agent 列表与详情查询
- WebSocket 实时推送
- Dashboard 总览与详情展示
- Mock Runner 持续模拟多 Agent 事件流

## 计划技术栈

- Backend：FastAPI、SQLAlchemy、SQLite、WebSocket
- Frontend：Vue 3、Vite、Tailwind CSS、Pinia
- Runner：Python CLI 原型，用于 mock 和后续 Hook 集成

## 目录结构

```text
agentboard/
  backend/
  frontend/
  runner/
  docs/
```

## 快速开始

1. 启动后端

```bash
cd backend
pip3 install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

如果前端不是从本机浏览器访问后端，记得额外配置 API 地址：

```bash
VITE_API_BASE_URL=http://your-server-ip:8000 npm run dev
```

3. 运行 mock runner

```bash
cd /path/to/agentboard
python3 runner/mock_runner.py --agents 3
```

如果你要验证通知体验，建议改用：

```bash
python3 runner/mock_runner.py --agents 3 --scenario attention
```

启动后可访问：

- 前端面板：`http://127.0.0.1:4173`
- 后端接口：`http://127.0.0.1:8000`

## 安装部署与接入

- 安装部署指南： [docs/install-and-cli-guide.md](docs/install-and-cli-guide.md)
- 真实 Agent 接入总说明： [docs/real-agent-integration-guide.md](docs/real-agent-integration-guide.md)
- 本地运行说明： [docs/local-runbook.md](docs/local-runbook.md)
- Claude Code Hooks 接入： [docs/claude-hooks-setup.md](docs/claude-hooks-setup.md)
- Codex Hooks 接入： [docs/codex-hooks-setup.md](docs/codex-hooks-setup.md)
- Runner 说明： [runner/README.md](runner/README.md)

如果你想用更短的命令接入真实 Codex，也可以直接运行仓库里的包装脚本：

```bash
cd /path/to/your/project
/path/to/agentboard/bin/codexb \
  --task "总结项目结构" \
  --prompt "请总结当前项目结构"
```

它会默认使用：

- `--backend http://127.0.0.1:8000`
- `--project` = 当前目录名
- `--cwd` = 当前目录

## 当前能力

- 后端 API：Agent 注册、事件上报、Agent 列表、详情、最近重要事件、WebSocket 广播
- 前端面板：总览、详情时间线、命令记录、文件修改、通知中心、提示音、强提醒
- Mock Runner：稳定模拟多 Agent 事件流
- 真实 Codex Runner：启动真实 `codex exec` 并持续上报
- 真实 Codex Hooks：接入长期交互式 Codex CLI 会话
- 通用 CLI Runner：接入 `Gemini CLI`、`cc`、`OpenCode` 等命令行 Agent
- Claude Hook Adapter：接入真实 Claude Code Hooks
- Workspace Watcher：自动上报文件创建、修改、删除

## 下一步规划

1. 搭建 backend 基础服务、核心数据模型和 API 路由。
2. 搭建 frontend 面板骨架，完成总览页和详情页。
3. 增加 mock runner，本地模拟多 Agent 实时活动。
4. 打通 backend 与 frontend 的 WebSocket 实时更新链路。
5. 在 MVP 稳定后接入 Claude Code Hook。
