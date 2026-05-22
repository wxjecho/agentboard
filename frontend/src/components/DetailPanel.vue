<script setup>
import { computed } from "vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps({
  detail: {
    type: Object,
    default: null,
  },
  isLoading: {
    type: Boolean,
    default: false,
  },
});

function formatTime(value) {
  if (!value) {
    return "暂无";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    month: "numeric",
    day: "numeric",
  }).format(new Date(value));
}

function formatDuration(value) {
  if (value == null) {
    return "暂无";
  }
  if (value < 1000) {
    return `${value} ms`;
  }
  return `${(value / 1000).toFixed(1)} s`;
}

function trimText(value, fallback = "暂无") {
  const text = String(value || "").trim();
  return text || fallback;
}

function summarizePayload(payload) {
  if (!payload) {
    return "无附加数据";
  }

  if (payload.command) {
    const exitCode = payload.exit_code == null ? "" : ` · 退出码 ${payload.exit_code}`;
    return `${payload.command}${exitCode}`;
  }

  if (payload.file_path) {
    return payload.file_path;
  }

  if (payload.content) {
    return trimText(payload.content, "无附加数据");
  }

  if (payload.status) {
    return `状态切换为 ${payload.status}`;
  }

  if (Object.keys(payload).length === 0) {
    return "无附加数据";
  }

  return JSON.stringify(payload, null, 2);
}

function getTimelineMeta(event) {
  const payload = event.payload || {};

  if (event.event_type === "waiting_input") {
    return {
      tone: "warn",
      label: "等待输入",
      title: "Agent 正在等待你确认",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "agent_failed") {
    return {
      tone: "danger",
      label: "失败",
      title: "任务执行失败",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "state_changed" && payload.status === "blocked") {
    return {
      tone: "danger",
      label: "卡住",
      title: "Agent 进入 blocked 状态",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "command_started") {
    return {
      tone: "info",
      label: "命令开始",
      title: "开始执行命令",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "command_finished") {
    return {
      tone: payload.exit_code && payload.exit_code !== 0 ? "warn" : "success",
      label: payload.exit_code && payload.exit_code !== 0 ? "命令异常" : "命令完成",
      title: payload.exit_code && payload.exit_code !== 0 ? "命令返回非零退出码" : "命令执行完成",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type.startsWith("file_")) {
    const actionMap = {
      file_created: "创建",
      file_modified: "修改",
      file_deleted: "删除",
    };
    return {
      tone: event.event_type === "file_deleted" ? "warn" : "success",
      label: `文件${actionMap[event.event_type] || "变更"}`,
      title: payload.file_path || "工作区文件发生变化",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "agent_finished") {
    return {
      tone: "success",
      label: "完成",
      title: "任务已完成",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "agent_started") {
    return {
      tone: "info",
      label: "启动",
      title: "Agent 已开始工作",
      summary: summarizePayload(payload),
    };
  }

  if (event.event_type === "heartbeat") {
    return {
      tone: "muted",
      label: "心跳",
      title: "Heartbeat",
      summary: "Agent 仍在持续上报活跃状态",
    };
  }

  return {
    tone: "muted",
    label: event.event_type,
    title: event.event_type,
    summary: summarizePayload(payload),
  };
}

const attentionSummary = computed(() => {
  const agent = props.detail?.agent;
  if (!agent) {
    return null;
  }

  if (agent.status === "blocked") {
    return {
      tone: "danger",
      title: "这个 Agent 当前卡住了",
      message: "它已经被标记为 blocked，建议优先查看最近命令和日志，判断是否需要重试或人工介入。",
    };
  }

  if (agent.status === "waiting_input") {
    return {
      tone: "warn",
      title: "这个 Agent 正在等你输入",
      message: "它需要你的确认或补充信息。尽快处理可以避免整条任务链停住。",
    };
  }

  if (agent.status === "failed") {
    return {
      tone: "danger",
      title: "这个 Agent 已经失败",
      message: "可以先看失败前后的命令和事件流，通常最快能定位问题发生在哪一步。",
    };
  }

  return null;
});

const timelineItems = computed(() =>
  (props.detail?.recent_events || []).map((event) => ({
    ...event,
    ...getTimelineMeta(event),
  }))
);
</script>

<template>
  <aside class="detail-panel">
    <div v-if="isLoading" class="detail-empty">正在加载详情...</div>
    <div v-else-if="!detail" class="detail-empty">选择一个 Agent 查看详情</div>
    <template v-else>
      <header class="detail-header">
        <div>
          <p class="detail-label">{{ detail.agent.agent_type }}</p>
          <h2>{{ detail.agent.task }}</h2>
        </div>
        <StatusBadge :status="detail.agent.status" />
      </header>

      <section class="detail-summary">
        <article>
          <span>Agent ID</span>
          <strong>{{ detail.agent.id }}</strong>
        </article>
        <article>
          <span>项目</span>
          <strong>{{ detail.agent.project }}</strong>
        </article>
        <article>
          <span>当前命令</span>
          <strong>{{ detail.agent.current_command || "暂无" }}</strong>
        </article>
        <article>
          <span>最后活跃</span>
          <strong>{{ formatTime(detail.agent.last_active_at) }}</strong>
        </article>
      </section>

      <section v-if="attentionSummary" class="detail-attention" :data-tone="attentionSummary.tone">
        <p class="section-label">Needs Attention</p>
        <h3>{{ attentionSummary.title }}</h3>
        <p>{{ attentionSummary.message }}</p>
      </section>

      <section class="detail-section">
        <div class="section-heading">
          <div>
            <p class="section-label">Event Timeline</p>
            <h3>关键时间线</h3>
          </div>
          <span>{{ timelineItems.length }} 条</span>
        </div>
        <ul class="timeline-list">
          <li v-for="event in timelineItems" :key="event.id" class="timeline-item" :data-tone="event.tone">
            <div class="timeline-dot"></div>
            <div class="timeline-card">
              <div class="timeline-meta">
                <span class="timeline-label">{{ event.label }}</span>
                <time>{{ formatTime(event.created_at) }}</time>
              </div>
              <strong>{{ event.title }}</strong>
              <p>{{ event.summary }}</p>
              <pre v-if="event.payload && Object.keys(event.payload).length > 1">{{ JSON.stringify(event.payload, null, 2) }}</pre>
            </div>
          </li>
        </ul>
      </section>

      <section class="detail-section">
        <div class="section-heading">
          <div>
            <p class="section-label">Commands</p>
            <h3>命令记录</h3>
          </div>
          <span>{{ detail.recent_command_logs.length }} 条</span>
        </div>
        <ul class="detail-list compact">
          <li v-for="command in detail.recent_command_logs" :key="command.id" class="detail-item detail-item-rich">
            <div class="detail-item-head">
              <strong>{{ command.command || "未识别命令" }}</strong>
              <time>{{ formatTime(command.created_at) }}</time>
            </div>
            <div class="detail-inline-metrics">
              <span class="inline-badge" :data-tone="command.exit_code && command.exit_code !== 0 ? 'warn' : 'neutral'">
                退出码：{{ command.exit_code ?? "暂无" }}
              </span>
              <span class="inline-badge" data-tone="neutral">耗时：{{ formatDuration(command.duration_ms) }}</span>
            </div>
          </li>
        </ul>
      </section>

      <section class="detail-section">
        <div class="section-heading">
          <div>
            <p class="section-label">Files</p>
            <h3>文件修改</h3>
          </div>
          <span>{{ detail.recent_file_changes.length }} 条</span>
        </div>
        <ul class="detail-list compact">
          <li v-for="change in detail.recent_file_changes" :key="change.id" class="detail-item detail-item-rich">
            <div class="detail-item-head">
              <strong>{{ change.file_path }}</strong>
              <time>{{ formatTime(change.created_at) }}</time>
            </div>
            <div class="detail-inline-metrics">
              <span class="inline-badge" :data-tone="change.change_type === 'deleted' ? 'warn' : 'success'">
                {{ change.change_type }}
              </span>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </aside>
</template>
