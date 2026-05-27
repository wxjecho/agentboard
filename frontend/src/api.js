function inferDefaultApiBaseUrl() {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }

  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  const hostname = window.location.hostname || "127.0.0.1";
  return `${protocol}//${hostname}:8000`;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || inferDefaultApiBaseUrl()).replace(/\/$/, "");

function makeWebSocketUrl() {
  const url = new URL(API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/agents";
  url.search = "";
  url.hash = "";
  return url.toString();
}

async function requestJson(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function getWebSocketUrl() {
  return makeWebSocketUrl();
}

export function fetchAgents() {
  return requestJson("/api/agents");
}

export function fetchAgentDetail(agentId) {
  return requestJson(`/api/agents/${encodeURIComponent(agentId)}`);
}

export function fetchRecentEvents(limit = 20) {
  return requestJson(`/api/events/recent?limit=${encodeURIComponent(limit)}`);
}
