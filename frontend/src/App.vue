<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";
import AgentCard from "./components/AgentCard.vue";
import DetailPanel from "./components/DetailPanel.vue";
import { useAgentsStore } from "./stores/agents";

const store = useAgentsStore();

const headline = computed(() => {
  if (store.agents.length === 0) {
    return "等待第一个 Agent 接入";
  }
  return `正在监控 ${store.agents.length} 个 Agent`;
});

const latestMessage = computed(() => store.recentBroadcasts[0] || null);
const notifications = computed(() => store.latestNotifications);
const missedNotifications = computed(() => store.latestMissedNotifications);
const toastNotifications = computed(() => store.toastNotifications);
const primaryActiveAlert = computed(() => store.primaryActiveAlert);
const browserNotificationActionLabel = computed(() => (
  store.browserNotificationsEnabled ? "关闭系统通知" : "开启系统通知"
));
const soundNotificationActionLabel = computed(() => (
  store.soundNotificationsEnabled ? "关闭提示音" : "开启提示音"
));

async function toggleBrowserNotifications() {
  if (store.browserNotificationsEnabled) {
    store.disableBrowserNotifications();
    return;
  }
  await store.requestBrowserNotifications();
}

async function toggleSoundNotifications() {
  if (store.soundNotificationsEnabled) {
    store.disableSoundNotifications();
    return;
  }
  await store.enableSoundNotifications();
}

function handleVisibilityChange() {
  store.setPageVisible(document.visibilityState === "visible");
}

function openAgent(agentId) {
  store.loadAgentDetail(agentId);
}

onMounted(async () => {
  await store.initialize();
  await store.syncSoundState();
  store.connectWebSocket();
  handleVisibilityChange();
  document.addEventListener("visibilitychange", handleVisibilityChange);
});

onBeforeUnmount(() => {
  store.disconnectWebSocket();
  document.removeEventListener("visibilitychange", handleVisibilityChange);
});
</script>

<template>
  <div class="page-shell">
    <section v-if="primaryActiveAlert" class="alert-banner" :data-level="primaryActiveAlert.level">
      <div>
        <p class="section-label">Critical Attention</p>
        <h2>{{ primaryActiveAlert.title }}</h2>
        <p class="alert-banner-copy">{{ primaryActiveAlert.message }}</p>
      </div>
      <div class="alert-banner-actions">
        <button class="solid-button" type="button" @click="store.acknowledgeAlert(primaryActiveAlert)">我来处理</button>
        <button class="ghost-button" type="button" @click="store.dismissNotification(primaryActiveAlert.id)">忽略提醒</button>
      </div>
    </section>

    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">AI Agent Monitor Platform</p>
        <h1>AgentBoard</h1>
        <p class="hero-text">
          用一块实时面板统一观察多 Agent 的状态、日志、命令和文件修改，快速判断谁在推进、谁在等待、谁需要你介入。
        </p>
      </div>

      <div class="hero-summary">
        <div class="summary-card strong">
          <span>监控概览</span>
          <strong>{{ headline }}</strong>
          <p>{{ store.describeConnection() }}</p>
        </div>
        <div class="summary-grid">
          <article class="summary-card">
            <span>活跃 Agent</span>
            <strong>{{ store.activeCount }}</strong>
          </article>
          <article class="summary-card">
            <span>待介入</span>
            <strong>{{ store.interventionCount }}</strong>
          </article>
          <article class="summary-card">
            <span>已完成</span>
            <strong>{{ store.doneCount }}</strong>
          </article>
        </div>

        <div class="summary-card notify-card">
          <div class="notify-card-head">
            <div>
              <span>主动通知</span>
              <strong>重要时刻把你叫回来</strong>
            </div>
            <div class="notify-actions">
              <button class="ghost-button" type="button" @click="toggleBrowserNotifications()">
                {{ browserNotificationActionLabel }}
              </button>
              <button class="ghost-button" type="button" @click="toggleSoundNotifications()">
                {{ soundNotificationActionLabel }}
              </button>
            </div>
          </div>
          <p>{{ store.describeBrowserNotifications() }}</p>
          <p>{{ store.describeSoundNotifications() }}</p>
          <p class="notify-tip">完成、失败、等待输入、命令异常会触发站内提醒，重要事件还会尝试发送浏览器通知。</p>
          <p class="notify-tip">{{ store.describeAttentionFallback() }}</p>
        </div>
      </div>
    </header>

    <main class="layout">
      <section class="feed-panel">
        <div class="panel-header">
          <div>
            <p class="section-label">Live Overview</p>
            <h2>Agent 总览</h2>
          </div>
          <button class="ghost-button" type="button" @click="store.initialize()">刷新列表</button>
        </div>

        <p v-if="store.error" class="error-banner">{{ store.error }}</p>
        <p v-else-if="store.isLoading" class="empty-state">正在加载 Agent 列表...</p>
        <p v-else-if="store.agents.length === 0" class="empty-state">
          暂时还没有 Agent。可以先启动后端，再运行 `python3 runner/mock_runner.py --agents 3` 看实时效果。
        </p>

        <div v-else class="agent-grid">
          <AgentCard
            v-for="agent in store.agents"
            :key="agent.id"
            :agent="agent"
            :is-selected="agent.id === store.selectedAgentId"
            @select="openAgent"
          />
        </div>

        <section class="broadcast-panel">
          <div class="panel-header compact">
            <div>
              <p class="section-label">Realtime Broadcast</p>
              <h3>最近推送</h3>
            </div>
            <span v-if="latestMessage">{{ latestMessage.type }}</span>
          </div>

          <pre v-if="latestMessage" class="broadcast-preview">{{ JSON.stringify(latestMessage, null, 2) }}</pre>
          <p v-else class="empty-state small">WebSocket 连接成功后，最新广播会显示在这里。</p>
        </section>

        <section class="broadcast-panel">
          <div class="panel-header compact">
            <div>
              <p class="section-label">Away Summary</p>
              <h3>离开期间</h3>
            </div>
            <button
              v-if="missedNotifications.length > 0"
              class="ghost-button"
              type="button"
              @click="store.clearMissedNotifications()"
            >
              标记已读
            </button>
          </div>

          <div v-if="missedNotifications.length === 0" class="empty-state small">
            你切换到别的页面时，重要事件会在这里留下摘要，方便回来后快速扫一眼。
          </div>

          <ul v-else class="notification-list">
            <li
              v-for="notice in missedNotifications"
              :key="`missed-${notice.id}`"
              class="notification-item"
              :data-level="notice.level"
            >
              <div>
                <strong>{{ notice.title }}</strong>
                <p>{{ notice.message }}</p>
              </div>
              <button class="icon-button" type="button" @click="store.dismissNotification(notice.id)">关闭</button>
            </li>
          </ul>
        </section>

        <section class="broadcast-panel">
          <div class="panel-header compact">
            <div>
              <p class="section-label">Notification Center</p>
              <h3>通知中心</h3>
            </div>
            <span>{{ notifications.length }} 条</span>
          </div>

          <div v-if="notifications.length === 0" class="empty-state small">
            暂时没有重要提醒。Agent 完成、失败或等待输入时，这里会主动记录。
          </div>

          <ul v-else class="notification-list">
            <li v-for="notice in notifications" :key="notice.id" class="notification-item" :data-level="notice.level">
              <div>
                <strong>{{ notice.title }}</strong>
                <p>{{ notice.message }}</p>
              </div>
              <div class="notification-actions">
                <button
                  v-if="notice.repeatable"
                  class="ghost-button slim"
                  type="button"
                  @click="store.acknowledgeAlert(notice)"
                >
                  我来处理
                </button>
                <button class="icon-button" type="button" @click="store.dismissNotification(notice.id)">关闭</button>
              </div>
            </li>
          </ul>
        </section>
      </section>

      <DetailPanel :detail="store.selectedAgentDetail" :is-loading="store.isDetailLoading" />
    </main>

    <div class="toast-stack" aria-live="polite">
      <article
        v-for="notice in toastNotifications"
        :key="`${notice.id}-toast`"
        class="toast-item"
        :data-level="notice.level"
      >
        <div>
          <strong>{{ notice.title }}</strong>
          <p>{{ notice.message }}</p>
        </div>
        <button class="icon-button" type="button" @click="store.dismissToast(notice.id)">关闭</button>
      </article>
    </div>
  </div>
</template>
