# 开发计划

## 目标

构建 AgentBoard 的本地优先 MVP，先跑通多 Agent 实时监控闭环，再逐步接入真实的生产级 Agent 适配与通知能力。

## 里程碑 1：本地 MVP

### Backend

- 搭建 FastAPI 应用入口
- 定义 Agent、Event、Command Log、File Change 的数据模型
- 实现 SQLite 持久化
- 实现 `POST /api/agents/register`
- 实现 `POST /api/events`
- 实现 `GET /api/agents`
- 实现 `GET /api/agents/{id}`
- 实现 `/ws/agents`
- 根据事件流推导 Agent 当前状态

### Frontend

- 搭建 Vue 3 + Vite 项目骨架
- 增加 dashboard 路由和基础布局
- 实现 Agent 总览页
- 实现 Agent 详情页或详情抽屉
- 订阅 WebSocket 实时流
- 展示状态、日志、命令和文件修改记录

### Runner

- 实现 mock runner CLI
- 模拟生命周期、日志、命令和文件修改事件
- 模拟 heartbeat、等待输入和完成流程
- 预留通用 CLI 包装器结构

## 里程碑 2：真实 Agent 接入

- 接入 Claude Code Hook 适配器
- 接入通用 CLI Runner 适配器
- 增加 workspace watcher 用于补采文件修改与活跃度
- 增加人工介入标记和卡住检测
- 增加通知能力

## 接入优先级

1. Claude Code：优先通过官方 Hooks 接入，跑通高质量事件链路。
2. Codex CLI：通过统一 runner 包装启动和上报，补齐当前高频使用场景。
3. Gemini CLI、cc、OpenCode：复用同一套通用 CLI 适配层，不单独设计后端协议。

## 备注

- Redis 在第一阶段不是必需，可以在本地实时链路稳定后再接入。
- SQLite 足够支撑第一版闭环验证。
- 后端事件模型必须保持通用，不能让某个 Agent 的专有字段直接污染整体协议。
