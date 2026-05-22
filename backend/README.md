# Backend

AgentBoard 后端负责接收 Agent 注册与事件上报、持久化运行数据、推导 Agent 当前状态，并通过 WebSocket 把实时变化广播给前端。

## 当前实现范围

- FastAPI 应用入口
- SQLite 持久化
- Agent / Event / Command Log / File Change 数据模型
- `POST /api/agents/register`
- `POST /api/events`
- `GET /api/agents`
- `GET /api/agents/{id}`
- `/ws/agents`

## 本地运行

安装依赖后可在 `backend` 目录运行：

```bash
uvicorn app.main:app --reload
```

默认数据库文件位于：

```text
backend/data/agentboard.db
```
