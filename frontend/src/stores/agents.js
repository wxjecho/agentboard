import { defineStore } from "pinia";
import { fetchAgentDetail, fetchAgents, fetchRecentEvents, getApiBaseUrl, getWebSocketUrl } from "../api";

const NOTIFICATION_STORAGE_KEY = "agentboard-browser-notifications";
const SOUND_STORAGE_KEY = "agentboard-sound-notifications";
const DEFAULT_TITLE = "AgentBoard";
const REPEAT_REMINDER_MS = 15000;
const repeatReminderTimers = new Map();

function getStatusPriority(status) {
  const priorities = {
    blocked: 0,
    waiting_input: 1,
    failed: 2,
    executing: 3,
    editing: 4,
    running: 5,
    thinking: 6,
    done: 7,
    idle: 8,
  };
  return priorities[status] ?? 9;
}

function sortAgents(items) {
  return [...items].sort((left, right) => {
    const leftPriority = getStatusPriority(left.status);
    const rightPriority = getStatusPriority(right.status);
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }

    if (left.needs_intervention !== right.needs_intervention) {
      return left.needs_intervention ? -1 : 1;
    }

    const leftTime = new Date(left.last_active_at || left.updated_at || 0).getTime();
    const rightTime = new Date(right.last_active_at || right.updated_at || 0).getTime();
    return rightTime - leftTime;
  });
}

function readNotificationPreference() {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(NOTIFICATION_STORAGE_KEY) === "enabled";
}

function readSoundPreference() {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(SOUND_STORAGE_KEY) === "enabled";
}

function writeNotificationPreference(enabled) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(NOTIFICATION_STORAGE_KEY, enabled ? "enabled" : "disabled");
}

function writeSoundPreference(enabled) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(SOUND_STORAGE_KEY, enabled ? "enabled" : "disabled");
}

function getBrowserPermission() {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "unsupported";
  }
  return window.Notification.permission;
}

function formatAgentLabel(agent) {
  if (!agent) {
    return "未知 Agent";
  }
  return `${agent.agent_type} · ${agent.task}`;
}

function createNotification({ level, title, message, agentId, sticky = false }) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    level,
    title,
    message,
    agentId: agentId || "",
    sticky,
    repeatable: sticky,
    eventKey: "",
    createdAt: new Date().toISOString(),
  };
}

function isHighAttentionLevel(level) {
  return level === "warn" || level === "danger" || level === "success";
}

function getAudioContextClass() {
  if (typeof window === "undefined") {
    return null;
  }
  return window.AudioContext || window.webkitAudioContext || null;
}

function buildNotificationFromMessage(message) {
  if (message.type !== "event_ingested" || !message.event || !message.agent) {
    return null;
  }

  return buildNotificationFromEventRecord({
    event: message.event,
    agent: message.agent,
  });
}

function buildNotificationFromEventRecord(record) {
  if (!record?.event || !record?.agent) {
    return null;
  }

  const { event, agent } = record;
  const label = formatAgentLabel(agent);
  const eventKey = `${event.id}`;

  if (event.event_type === "agent_finished") {
    return {
      ...createNotification({
      level: "success",
      title: "任务完成",
      message: `${label} 已完成本轮任务。`,
      agentId: agent.id,
      }),
      eventKey,
      createdAt: event.created_at || new Date().toISOString(),
    };
  }

  if (event.event_type === "agent_failed") {
    return {
      ...createNotification({
      level: "danger",
      title: "任务失败",
      message: `${label} 失败了，建议立即查看详情。`,
      agentId: agent.id,
      sticky: true,
      }),
      eventKey,
      createdAt: event.created_at || new Date().toISOString(),
    };
  }

  if (event.event_type === "waiting_input") {
    return {
      ...createNotification({
      level: "warn",
      title: "等待你的输入",
      message: `${label} 正在等待人工确认。`,
      agentId: agent.id,
      sticky: true,
      }),
      eventKey,
      createdAt: event.created_at || new Date().toISOString(),
    };
  }

  if (event.event_type === "command_finished" && event.payload?.exit_code && event.payload.exit_code !== 0) {
    return {
      ...createNotification({
      level: "warn",
      title: "命令执行异常",
      message: `${label} 执行 ${event.payload.command || "命令"} 时返回非零退出码。`,
      agentId: agent.id,
      }),
      eventKey,
      createdAt: event.created_at || new Date().toISOString(),
    };
  }

  return null;
}

export const useAgentsStore = defineStore("agents", {
  state: () => ({
    agents: [],
    selectedAgentId: "",
    selectedAgentDetail: null,
    isLoading: false,
    isDetailLoading: false,
    error: "",
    socketStatus: "disconnected",
    recentBroadcasts: [],
    notifications: [],
    toastNotifications: [],
    missedNotifications: [],
    activeAlerts: [],
    socket: null,
    browserNotificationsEnabled: readNotificationPreference(),
    browserPermission: getBrowserPermission(),
    soundNotificationsEnabled: readSoundPreference(),
    soundReady: false,
    audioContext: null,
    pageVisible: true,
    unseenHighAttentionCount: 0,
  }),

  getters: {
    selectedAgent(state) {
      return state.agents.find((item) => item.id === state.selectedAgentId) || null;
    },
    activeCount(state) {
      return state.agents.filter((item) => !["done", "failed"].includes(item.status)).length;
    },
    interventionCount(state) {
      return state.agents.filter((item) => item.needs_intervention).length;
    },
    doneCount(state) {
      return state.agents.filter((item) => item.status === "done").length;
    },
    latestNotifications(state) {
      return state.notifications.slice(0, 6);
    },
    latestMissedNotifications(state) {
      return state.missedNotifications.slice(0, 5);
    },
    primaryActiveAlert(state) {
      return state.activeAlerts[0] || null;
    },
  },

  actions: {
    async initialize() {
      this.isLoading = true;
      this.error = "";

      try {
        const response = await fetchAgents();
        this.agents = sortAgents(response.items);
        await this.loadRecentImportantEvents();
        if (!this.selectedAgentId && this.agents.length > 0) {
          this.selectedAgentId = this.agents[0].id;
        }
        if (this.selectedAgentId) {
          await this.loadAgentDetail(this.selectedAgentId);
        }
      } catch (error) {
        this.error = error instanceof Error ? error.message : "加载 Agent 列表失败";
      } finally {
        this.isLoading = false;
      }
    },

    async loadRecentImportantEvents() {
      try {
        const response = await fetchRecentEvents(12);
        const notices = response.items
          .map((item) => buildNotificationFromEventRecord(item))
          .filter(Boolean)
          .reverse();

        for (const notice of notices) {
          this.addNotificationRecord(notice, { showToast: false, preserveMissed: true });
        }
      } catch {
        // Keep startup resilient even if the backfill endpoint is temporarily unavailable.
      }
    },

    async loadAgentDetail(agentId) {
      this.selectedAgentId = agentId;
      this.isDetailLoading = true;

      try {
        this.selectedAgentDetail = await fetchAgentDetail(agentId);
      } catch (error) {
        this.error = error instanceof Error ? error.message : "加载 Agent 详情失败";
      } finally {
        this.isDetailLoading = false;
      }
    },

    upsertAgent(agent) {
      const index = this.agents.findIndex((item) => item.id === agent.id);
      if (index === -1) {
        this.agents = sortAgents([agent, ...this.agents]);
      } else {
        const next = [...this.agents];
        next[index] = { ...next[index], ...agent };
        this.agents = sortAgents(next);
      }
    },

    async refreshSelectedAgent() {
      if (!this.selectedAgentId) {
        return;
      }
      await this.loadAgentDetail(this.selectedAgentId);
    },

    pushBroadcast(message) {
      this.recentBroadcasts = [message, ...this.recentBroadcasts].slice(0, 10);
    },

    addNotificationRecord(notification, options = {}) {
      if (notification.eventKey && this.notifications.some((item) => item.eventKey === notification.eventKey)) {
        return;
      }

      this.notifications = [notification, ...this.notifications].slice(0, 100);

      if (options.showToast !== false) {
        this.toastNotifications = [notification, ...this.toastNotifications].slice(0, 4);
      }

      if (!this.pageVisible && isHighAttentionLevel(notification.level) && options.preserveMissed !== false) {
        this.unseenHighAttentionCount += 1;
        this.missedNotifications = [notification, ...this.missedNotifications].slice(0, 20);
        this.updateDocumentTitle();
      }

      if (notification.repeatable) {
        this.upsertActiveAlert(notification);
      }
    },

    pushNotification(notification) {
      this.addNotificationRecord(notification, { showToast: true, preserveMissed: true });
      if (!notification.sticky) {
        window.setTimeout(() => {
          this.dismissToast(notification.id);
        }, 5200);
      }
    },

    dismissToast(notificationId) {
      this.toastNotifications = this.toastNotifications.filter((item) => item.id !== notificationId);
    },

    upsertActiveAlert(notification) {
      const index = this.activeAlerts.findIndex((item) => item.eventKey === notification.eventKey);
      if (index === -1) {
        this.activeAlerts = [notification, ...this.activeAlerts];
      } else {
        const next = [...this.activeAlerts];
        next[index] = notification;
        this.activeAlerts = next;
      }
      this.scheduleRepeatReminder(notification);
    },

    clearRepeatReminder(eventKey) {
      const timerId = repeatReminderTimers.get(eventKey);
      if (timerId) {
        window.clearTimeout(timerId);
        repeatReminderTimers.delete(eventKey);
      }
    },

    scheduleRepeatReminder(notification) {
      if (!notification.repeatable || !notification.eventKey) {
        return;
      }

      this.clearRepeatReminder(notification.eventKey);

      const timerId = window.setTimeout(() => {
        const stillActive = this.activeAlerts.find((item) => item.eventKey === notification.eventKey);
        if (!stillActive) {
          this.clearRepeatReminder(notification.eventKey);
          return;
        }

        const reminder = {
          ...stillActive,
          id: `${stillActive.eventKey}-repeat-${Date.now()}`,
          title: stillActive.level === "danger" ? "仍需处理的失败任务" : "仍在等待你的确认",
          message:
            stillActive.level === "danger"
              ? `${stillActive.message} 这条失败提醒仍未确认。`
              : `${stillActive.message} 这条等待输入提醒仍未确认。`,
          sticky: true,
          repeatable: false,
        };

        this.toastNotifications = [reminder, ...this.toastNotifications].slice(0, 4);
        this.playNotificationSound(reminder);
        this.sendBrowserNotification(reminder);
        this.scheduleRepeatReminder(stillActive);
      }, REPEAT_REMINDER_MS);

      repeatReminderTimers.set(notification.eventKey, timerId);
    },

    acknowledgeAlert(notification) {
      if (!notification) {
        return;
      }

      if (notification.agentId) {
        this.loadAgentDetail(notification.agentId);
      }

      if (notification.eventKey) {
        this.clearRepeatReminder(notification.eventKey);
        this.activeAlerts = this.activeAlerts.filter((item) => item.eventKey !== notification.eventKey);
      }

      this.dismissNotification(notification.id);
    },

    dismissNotification(notificationId) {
      const target = this.notifications.find((item) => item.id === notificationId)
        || this.activeAlerts.find((item) => item.id === notificationId)
        || this.toastNotifications.find((item) => item.id === notificationId)
        || this.missedNotifications.find((item) => item.id === notificationId);
      if (target?.eventKey) {
        this.clearRepeatReminder(target.eventKey);
        this.activeAlerts = this.activeAlerts.filter((item) => item.eventKey !== target.eventKey);
      }
      this.dismissToast(notificationId);
      this.missedNotifications = this.missedNotifications.filter((item) => item.id !== notificationId);
      this.notifications = this.notifications.filter((item) => item.id !== notificationId);
    },

    async requestBrowserNotifications() {
      if (typeof window === "undefined" || !("Notification" in window)) {
        this.browserPermission = "unsupported";
        return;
      }

      const permission = await window.Notification.requestPermission();
      this.browserPermission = permission;
      this.browserNotificationsEnabled = permission === "granted";
      writeNotificationPreference(this.browserNotificationsEnabled);
    },

    disableBrowserNotifications() {
      this.browserNotificationsEnabled = false;
      writeNotificationPreference(false);
    },

    async enableSoundNotifications() {
      const AudioContextClass = getAudioContextClass();
      if (!AudioContextClass) {
        this.soundReady = false;
        return false;
      }

      if (!this.audioContext) {
        this.audioContext = new AudioContextClass();
      }

      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }

      this.soundNotificationsEnabled = true;
      this.soundReady = this.audioContext.state === "running";
      writeSoundPreference(this.soundNotificationsEnabled);
      return this.soundReady;
    },

    disableSoundNotifications() {
      this.soundNotificationsEnabled = false;
      this.soundReady = false;
      writeSoundPreference(false);
    },

    async syncSoundState() {
      if (!this.soundNotificationsEnabled) {
        this.soundReady = false;
        return;
      }

      const AudioContextClass = getAudioContextClass();
      if (!AudioContextClass) {
        this.soundReady = false;
        return;
      }

      if (!this.audioContext) {
        this.audioContext = new AudioContextClass();
      }

      this.soundReady = this.audioContext.state === "running";
    },

    async playNotificationSound(notification) {
      if (!this.soundNotificationsEnabled) {
        return;
      }

      const AudioContextClass = getAudioContextClass();
      if (!AudioContextClass) {
        return;
      }

      if (!this.audioContext) {
        this.audioContext = new AudioContextClass();
      }

      if (this.audioContext.state !== "running") {
        this.soundReady = false;
        return;
      }

      this.soundReady = true;

      const patterns = {
        success: [
          [880, 0, 0.08],
          [1174, 0.1, 0.12],
        ],
        warn: [
          [720, 0, 0.12],
          [720, 0.18, 0.12],
        ],
        danger: [
          [640, 0, 0.14],
          [520, 0.18, 0.16],
          [440, 0.38, 0.2],
        ],
      };

      const pattern = patterns[notification.level] || patterns.warn;
      const now = this.audioContext.currentTime;

      for (const [frequency, offset, duration] of pattern) {
        const oscillator = this.audioContext.createOscillator();
        const gainNode = this.audioContext.createGain();

        oscillator.type = notification.level === "danger" ? "sawtooth" : "sine";
        oscillator.frequency.setValueAtTime(frequency, now + offset);

        gainNode.gain.setValueAtTime(0.0001, now + offset);
        gainNode.gain.exponentialRampToValueAtTime(0.11, now + offset + 0.02);
        gainNode.gain.exponentialRampToValueAtTime(0.0001, now + offset + duration);

        oscillator.connect(gainNode);
        gainNode.connect(this.audioContext.destination);
        oscillator.start(now + offset);
        oscillator.stop(now + offset + duration + 0.02);
      }
    },

    sendBrowserNotification(notification) {
      if (
        typeof window === "undefined" ||
        !("Notification" in window) ||
        !this.browserNotificationsEnabled ||
        this.browserPermission !== "granted"
      ) {
        return;
      }

      const systemNotice = new window.Notification(notification.title, {
        body: notification.message,
        tag: notification.agentId || notification.title,
        requireInteraction: notification.sticky,
      });

      systemNotice.onclick = () => {
        window.focus();
        if (notification.agentId) {
          this.loadAgentDetail(notification.agentId);
        }
        if (notification.repeatable) {
          this.acknowledgeAlert(notification);
        }
      };
    },

    handleRealtimeNotification(message) {
      const notification = buildNotificationFromMessage(message);
      if (!notification) {
        return;
      }
      this.pushNotification(notification);
      this.playNotificationSound(notification);
      this.sendBrowserNotification(notification);
    },

    connectWebSocket() {
      if (this.socket) {
        this.socket.close();
      }

      const socket = new WebSocket(getWebSocketUrl());
      this.socket = socket;
      this.socketStatus = "connecting";

      socket.addEventListener("open", () => {
        this.socketStatus = "connected";
      });

      socket.addEventListener("message", async (event) => {
        const message = JSON.parse(event.data);
        this.pushBroadcast(message);
        this.handleRealtimeNotification(message);

        if (message.agent) {
          this.upsertAgent(message.agent);
        }

        if (message.agent?.id && message.agent.id === this.selectedAgentId) {
          await this.refreshSelectedAgent();
        }
      });

      socket.addEventListener("close", () => {
        this.socketStatus = "disconnected";
      });

      socket.addEventListener("error", () => {
        this.socketStatus = "error";
      });
    },

    disconnectWebSocket() {
      if (this.socket) {
        this.socket.close();
        this.socket = null;
      }
      this.socketStatus = "disconnected";
    },

    describeConnection() {
      return `${this.socketStatus} · ${getApiBaseUrl()}`;
    },

    setPageVisible(visible) {
      this.pageVisible = visible;
      if (visible) {
        this.clearAttentionState();
      } else {
        this.updateDocumentTitle();
      }
    },

    clearAttentionState() {
      this.unseenHighAttentionCount = 0;
      this.updateDocumentTitle();
    },

    clearMissedNotifications() {
      this.missedNotifications = [];
      this.clearAttentionState();
    },

    updateDocumentTitle() {
      if (typeof document === "undefined") {
        return;
      }
      if (this.unseenHighAttentionCount > 0) {
        document.title = `(${this.unseenHighAttentionCount}) ${DEFAULT_TITLE} · 需要注意`;
        return;
      }
      document.title = DEFAULT_TITLE;
    },

    describeBrowserNotifications() {
      if (this.browserPermission === "unsupported") {
        return "当前浏览器不支持系统通知";
      }
      if (this.browserPermission === "granted" && this.browserNotificationsEnabled) {
        return "系统通知已开启";
      }
      if (this.browserPermission === "denied") {
        return "系统通知已被浏览器拒绝";
      }
      return "系统通知未开启";
    },

    describeSoundNotifications() {
      if (!getAudioContextClass()) {
        return "当前浏览器不支持提示音";
      }
      if (!this.soundNotificationsEnabled) {
        return "提示音未开启";
      }
      if (!this.soundReady) {
        return "提示音已授权，等待你与页面交互后生效";
      }
      return "提示音已开启";
    },

    describeAttentionFallback() {
      if (this.pageVisible) {
        return "当前页可见，重要事件会直接弹出提醒。";
      }
      if (this.browserPermission === "granted" && this.browserNotificationsEnabled) {
        return "当前页隐藏中，系统通知和标签标题角标会继续提醒你。";
      }
      return "当前页隐藏中，标签标题会显示未读提醒数，回到页面后还能看到离开期间的通知摘要。";
    },
  },
});
