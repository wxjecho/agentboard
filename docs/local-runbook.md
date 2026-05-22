# 本地运行说明

## 目标

在本机启动 AgentBoard，并验证三类数据源：

- 后端 API
- 前端 Dashboard
- Mock Runner / 真实 Runner / Claude Hooks

## 1. 启动后端

进入后端目录：

```bash
cd /Users/wuxinji/code/agentboard/backend
```

安装依赖：

```bash
pip3 install -r requirements.txt
```

启动服务：

```bash
uvicorn app.main:app --reload
```

默认地址：

```text
http://127.0.0.1:8000
```

可用接口：

- `GET /health`
- `POST /api/agents/register`
- `POST /api/events`
- `GET /api/agents`
- `GET /api/agents/{agent_id}`
- `WS /ws/agents`

## 2. 启动前端

进入前端目录：

```bash
cd /Users/wuxinji/code/agentboard/frontend
```

安装依赖：

```bash
npm install
```

启动开发服务：

```bash
npm run dev
```

默认地址：

```text
http://127.0.0.1:4173
```

如果后端地址不是默认值，可以在 `frontend` 目录创建 `.env`：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 3. 启动 Mock Runner

回到仓库根目录：

```bash
cd /Users/wuxinji/code/agentboard
```

运行模拟事件流：

```bash
python3 runner/mock_runner.py --agents 3
```

如果想稳定验证通知、离开期间摘要和标题未读提醒，建议使用：

```bash
python3 runner/mock_runner.py --agents 3 --scenario attention
```

只想预览事件，不发请求：

```bash
python3 runner/mock_runner.py --agents 2 --interval 0 --dry-run
```

## 4. 预期效果

- 前端打开后能看到 Agent 列表
- Mock Runner 启动后会注册多个 Agent
- Agent 状态会随着事件流实时变化
- 详情侧栏能看到事件、命令记录和文件修改
- 右侧或底部区域能看到最新 WebSocket 广播

## 5. 真实 Runner 验证

### Codex

```bash
cd /Users/wuxinji/code/agentboard
python3 runner/codex_runner.py \
  --backend http://127.0.0.1:8000 \
  --project agentboard \
  --task "验证真实 Codex 接入" \
  --cwd /Users/wuxinji/code/agentboard \
  --prompt "请总结当前项目结构"
```

### 通用 CLI

```bash
cd /Users/wuxinji/code/agentboard
python3 runner/generic_cli_runner.py \
  --backend http://127.0.0.1:8000 \
  --agent-type cc \
  --project agentboard \
  --task "验证通用 CLI 接入" \
  --cwd /Users/wuxinji/code/agentboard \
  -- \
  cc "请总结当前项目结构"
```

### Claude Hooks

完整说明见：

- [docs/claude-hooks-setup.md](/Users/wuxinji/code/agentboard/docs/claude-hooks-setup.md)

## 6. 当前已知边界

- 当前使用 SQLite，适合本地 MVP
- 真实 `Codex` 已验证接入，`Claude Hooks` 和通用 CLI runner 已完成实现
- `generic_cli_runner` 对不同 CLI 的“等待输入”和“卡住”识别仍属于启发式规则
- 当前没有做认证、多用户和外部通知通道
