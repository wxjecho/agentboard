<script setup>
import StatusBadge from "./StatusBadge.vue";

defineProps({
  agent: {
    type: Object,
    required: true,
  },
  isSelected: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["select"]);

function formatTime(value) {
  if (!value) {
    return "暂无";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    month: "numeric",
    day: "numeric",
  }).format(new Date(value));
}

function getAttentionTone(agent) {
  if (agent.status === "blocked" || agent.status === "failed") {
    return "danger";
  }
  if (agent.status === "waiting_input" || agent.needs_intervention) {
    return "warn";
  }
  if (agent.status === "done") {
    return "success";
  }
  return "neutral";
}

function getAttentionTitle(agent) {
  if (agent.status === "blocked") {
    return "已卡住，建议立刻介入";
  }
  if (agent.status === "waiting_input") {
    return "正在等你确认";
  }
  if (agent.status === "failed") {
    return "执行失败，需要排查";
  }
  if (agent.status === "done") {
    return "本轮任务已完成";
  }
  return "运行平稳";
}
</script>

<template>
  <button
    class="agent-card"
    :class="{ selected: isSelected, urgent: agent.status === 'blocked' || agent.status === 'waiting_input' }"
    :data-tone="getAttentionTone(agent)"
    type="button"
    @click="$emit('select', agent.id)"
  >
    <div class="agent-attention-rail"></div>
    <div class="agent-card-top">
      <div>
        <p class="agent-type">{{ agent.agent_type }}</p>
        <h3>{{ agent.task }}</h3>
      </div>
      <StatusBadge :status="agent.status" />
    </div>

    <p class="agent-project">{{ agent.project }} · {{ agent.id }}</p>
    <p class="agent-command">{{ agent.current_command || "当前没有执行命令" }}</p>

    <div class="agent-meta">
      <span>最后活跃：{{ formatTime(agent.last_active_at) }}</span>
      <span class="agent-health" :data-tone="getAttentionTone(agent)">{{ getAttentionTitle(agent) }}</span>
    </div>
  </button>
</template>
