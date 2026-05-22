<script setup>
const props = defineProps({
  status: {
    type: String,
    default: "idle",
  },
});

const labels = {
  idle: "空闲",
  running: "运行中",
  thinking: "思考中",
  editing: "编辑中",
  executing: "执行中",
  waiting_input: "等待输入",
  blocked: "已卡住",
  failed: "失败",
  done: "完成",
};
</script>

<template>
  <span class="status-badge" :data-status="props.status">
    {{ labels[props.status] || props.status }}
  </span>
</template>
