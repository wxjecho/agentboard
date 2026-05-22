# Frontend

`frontend` 目录用于承载 AgentBoard 的实时监控面板。

## 当前实现

当前版本基于 Vue 3 + Vite + Pinia，已经提供：

- Agent 总览卡片列表
- 关键指标统计
- Agent 详情侧栏
- 最近事件、命令记录、文件修改记录展示
- 基于 WebSocket 的实时刷新
- 站内通知中心和浮层提醒
- Agent 完成、失败、等待输入、命令异常时的浏览器系统通知
- 基于环境变量配置后端地址

## 本地运行

进入 `frontend` 目录后：

```bash
npm install
npm run dev
```

默认读取：

```text
http://127.0.0.1:8000
```

如果需要改成其他后端地址，可创建 `.env`：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```
