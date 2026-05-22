# Agent 接入与上报设计

## 目标

AgentBoard 需要接入多个 AI Coding Agent，并把不同来源的运行信息统一转换成标准事件，供后端存储、状态推导和前端展示使用。

设计重点有三点：

- 不同 Agent 的接入方式可以不同，但上报协议必须统一
- 原始事件和推导状态分离，避免前端直接依赖某个 Agent 的内部语义
- 新增 Agent 时优先增加适配器，而不是修改后端核心模型

## 接入分层

### 1. Native Hook Adapter

适用于原生支持 Hook、生命周期回调或事件命令触发的 Agent。

特点：

- 接入成本低
- 事件精度高
- 能较准确地感知命令执行、编辑行为和等待输入状态

首批目标：

- Claude Code

### 2. Wrapper Runner Adapter

适用于没有完整 Hook 能力，但可以通过统一入口启动的 CLI Agent。

典型用法：

```bash
agentboard run codex --project agentboard --task "实现 agent 列表页"
```

特点：

- 统一进程生命周期管理
- 可采集 stdout、stderr、退出码、运行时长、工作目录
- 可与后端注册、心跳、结束上报天然联动

首批目标：

- Codex CLI
- Gemini CLI
- cc
- OpenCode
- 其他命令行 Agent

### 3. Workspace Watch Adapter

适用于作为旁路补充采集器，不直接替代 Hook 或 Runner。

职责：

- 监听工作目录文件修改
- 补采文件创建、修改、删除事件
- 辅助判断 Agent 是否长时间无活跃
- 为后续 diff 摘要与介入分析提供基础

## 首批接入策略

第一阶段不追求“一次性接完所有 Agent”，而是采用分批落地策略：

1. Claude Code 通过 Hook 接入，先建立高质量标准事件样本。
2. Codex CLI 通过通用 Runner 接入，验证统一包装器思路。
3. Gemini CLI、cc、OpenCode 复用通用 Runner 适配层。
4. 文件修改统一由 Workspace Watcher 补采，避免每个 Agent 单独实现文件跟踪。

## 统一上报协议

所有适配器最终都向后端发送统一事件，不直接把 Agent 原始字段写入数据库。

### Agent 注册

`POST /api/agents/register`

建议载荷：

```json
{
  "agent_id": "agent-001",
  "agent_type": "codex",
  "project": "agentboard",
  "task": "实现 dashboard 总览页",
  "cwd": "/workspace/agentboard",
  "source": "runner",
  "started_at": "2026-05-21T12:00:00Z"
}
```

### 事件上报

`POST /api/events`

基础公共字段：

```json
{
  "agent_id": "agent-001",
  "agent_type": "codex",
  "project": "agentboard",
  "task": "实现 dashboard 总览页",
  "event_type": "command_finished",
  "timestamp": "2026-05-21T12:01:20Z",
  "payload": {}
}
```

说明：

- `agent_id` 由 runner 或 hook 会话生成
- `agent_type` 标识来源类型，如 `claude-code`、`codex`、`gemini-cli`
- `event_type` 为统一枚举，不允许随 Agent 自定义
- `payload` 用于承载该事件的扩展字段

## 标准事件类型

建议 MVP 先支持以下事件：

- `agent_started`
- `heartbeat`
- `state_changed`
- `log`
- `command_started`
- `command_finished`
- `file_created`
- `file_modified`
- `file_deleted`
- `waiting_input`
- `agent_finished`
- `agent_failed`

### 事件载荷示例

`log`

```json
{
  "event_type": "log",
  "payload": {
    "stream": "stdout",
    "content": "Running tests..."
  }
}
```

`command_finished`

```json
{
  "event_type": "command_finished",
  "payload": {
    "command": "npm test",
    "exit_code": 1,
    "duration_ms": 5320
  }
}
```

`file_modified`

```json
{
  "event_type": "file_modified",
  "payload": {
    "file_path": "frontend/src/views/AgentList.vue",
    "change_type": "modified"
  }
}
```

## 状态推导策略

前端展示的 Agent 状态不应完全依赖原始上报，而应由后端基于统一事件流进行推导。

### 目标状态

- `idle`
- `running`
- `thinking`
- `editing`
- `executing`
- `waiting_input`
- `blocked`
- `failed`
- `done`

### 推导原则

- 收到 `agent_started` 后进入 `running`
- 收到命令开始事件后进入 `executing`
- 收到文件修改事件后进入 `editing`
- 收到等待输入事件后进入 `waiting_input`
- 命令结束后回到 `running` 或 `thinking`
- 长时间无日志且无 heartbeat 时进入 `blocked`
- 收到失败事件后进入 `failed`
- 收到完成事件后进入 `done`

说明：

- `thinking` 通常不是 Agent 原生显式上报，而是由“运行中但近期没有命令和文件操作”推导得出
- `blocked` 需要基于超时阈值与最后活跃时间判断

## 各类 Agent 的映射建议

### Claude Code

接入方式：

- 使用官方 Hooks

建议映射：

- `SessionStart` -> `agent_started`
- `PreToolUse` -> `command_started` 或 `state_changed`
- `PostToolUse` -> `command_finished`、`file_modified`
- `Notification` -> `waiting_input`
- `Stop` -> `agent_finished`

### Codex CLI

接入方式：

- 使用 `agentboard run codex ...` 包装启动

可采集信息：

- 启动时间
- 标准输出和错误输出
- 心跳
- 退出码
- 工作目录
- 子命令信息

补充采集：

- 文件修改由 workspace watcher 补采

### Gemini CLI / cc / OpenCode

接入方式：

- 统一纳入通用 CLI Runner

原则：

- 在适配器层处理命令参数差异
- 不为每个 Agent 单独设计后端存储结构
- 仅在需要时扩展解析器识别特定日志模式

## 后端职责边界

后端需要做三件事：

1. 接收并持久化标准事件
2. 根据事件更新 Agent 当前状态与最近活跃时间
3. 通过 WebSocket 向前端广播增量变化

后端不负责：

- 解析某个 Agent 的全部内部协议
- 直接启动所有 Agent 进程
- 把适配逻辑写死在核心业务模型中

## Runner 职责边界

Runner 或 Hook Adapter 负责：

- 生成或传递 `agent_id`
- 采集原始运行信息
- 转换成统一事件
- 向后端可靠上报

Runner 不负责：

- 直接渲染展示逻辑
- 维护最终状态机
- 绕过统一协议直接写数据库

## MVP 必须先跑通的五类信号

第一版最关键的是先稳定采集以下五类信号：

- Agent 启动与结束
- Heartbeat
- 日志流
- 命令执行
- 文件修改

只要这五类信号稳定，监控面板就具备基础可用性，后续再补等待输入、通知、卡住检测和更细粒度的状态判断。
