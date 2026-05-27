from __future__ import annotations

import argparse
import json
import random
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_BACKEND = "http://127.0.0.1:8000"
DEFAULT_AGENT_TYPES = ["codex", "claude-code", "gemini-cli", "cc", "opencode"]
DEFAULT_TASKS = [
    "实现 Agent 总览页",
    "补齐 WebSocket 实时推送",
    "重构事件模型与状态机",
    "接入 Claude Code Hook 适配器",
    "实现文件修改跟踪",
]
DEFAULT_COMMANDS = [
    "npm run dev",
    "npm test",
    "pytest",
    "uvicorn app.main:app --reload",
    "pnpm lint",
]
DEFAULT_FILES = [
    "frontend/src/views/AgentOverview.vue",
    "frontend/src/components/StatusPill.vue",
    "backend/app/services.py",
    "backend/app/main.py",
    "runner/mock_runner.py",
    "docs/agent-integration-design.md",
]
DEFAULT_LOG_LINES = [
    "Analyzing current task requirements...",
    "Planning next code changes.",
    "Running local checks.",
    "Applying patch to the target files.",
    "Reviewing command output for regressions.",
]
WAITING_PROMPTS = [
    "需要你确认数据库字段命名是否保持兼容。",
    "等待你确认是否启用 Redis。",
    "需要你决定前端是否先做详情抽屉。",
]
SCENARIO_TYPES = ("standard", "attention")


@dataclass
class MockAgent:
    agent_id: str
    agent_type: str
    project: str
    task: str
    cwd: str


class BackendClient:
    def __init__(self, backend: str, dry_run: bool = False) -> None:
        self.backend = backend.rstrip("/")
        self.dry_run = dry_run

    def register_agent(self, agent: MockAgent) -> None:
        payload = {
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type,
            "project": agent.project,
            "task": agent.task,
            "cwd": agent.cwd,
            "source": "runner",
            "started_at": iso_now(),
        }
        self._post("/api/agents/register", payload)

    def send_event(self, agent: MockAgent, event_type: str, payload: dict[str, Any] | None = None) -> None:
        body = {
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type,
            "project": agent.project,
            "task": agent.task,
            "cwd": agent.cwd,
            "event_type": event_type,
            "timestamp": iso_now(),
            "payload": payload or {},
        }
        self._post("/api/events", body)

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        if self.dry_run:
            print(f"[dry-run] POST {path} {json.dumps(payload, ensure_ascii=False)}")
            return

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.backend}{path}",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                response.read()
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {path}: {body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Unable to reach backend {self.backend}: {exc.reason}") from exc


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_agent(project: str, cwd: str, index: int) -> MockAgent:
    agent_type = DEFAULT_AGENT_TYPES[index % len(DEFAULT_AGENT_TYPES)]
    task = DEFAULT_TASKS[index % len(DEFAULT_TASKS)]
    slug = uuid.uuid4().hex[:8]
    return MockAgent(
        agent_id=f"{agent_type}-{slug}",
        agent_type=agent_type,
        project=project,
        task=task,
        cwd=cwd,
    )


def emit_standard_flow(client: BackendClient, agent: MockAgent, interval: float) -> None:
    client.register_agent(agent)
    sleep(interval)

    client.send_event(agent, "agent_started")
    sleep(interval)

    client.send_event(agent, "heartbeat")
    sleep(interval)

    client.send_event(
        agent,
        "log",
        {
            "stream": "stdout",
            "content": random.choice(DEFAULT_LOG_LINES),
        },
    )
    sleep(interval)

    command = random.choice(DEFAULT_COMMANDS)
    client.send_event(
        agent,
        "command_started",
        {
            "command": command,
        },
    )
    sleep(interval)

    client.send_event(
        agent,
        "file_modified",
        {
            "file_path": random.choice(DEFAULT_FILES),
            "change_type": "modified",
        },
    )
    sleep(interval)

    if random.random() < 0.35:
        client.send_event(
            agent,
            "waiting_input",
            {
                "message": random.choice(WAITING_PROMPTS),
            },
        )
        sleep(interval)
        client.send_event(agent, "heartbeat")
        sleep(interval)

    exit_code = 1 if random.random() < 0.18 else 0
    client.send_event(
        agent,
        "command_finished",
        {
            "command": command,
            "exit_code": exit_code,
            "duration_ms": random.randint(500, 8000),
        },
    )
    sleep(interval)

    if exit_code == 0:
        client.send_event(
            agent,
            "log",
            {
                "stream": "stdout",
                "content": "Command completed successfully.",
            },
        )
        sleep(interval)
        client.send_event(agent, "agent_finished")
    else:
        client.send_event(
            agent,
            "log",
            {
                "stream": "stderr",
                "content": "Command failed, intervention may be required.",
            },
        )
        sleep(interval)
        client.send_event(
            agent,
            "agent_failed",
            {
                "reason": "mock command exited with non-zero status",
            },
        )


def emit_attention_flow(client: BackendClient, agent: MockAgent, interval: float, index: int) -> None:
    client.register_agent(agent)
    sleep(interval)
    client.send_event(agent, "agent_started")
    sleep(interval)
    client.send_event(agent, "heartbeat")
    sleep(interval)

    if index % 3 == 0:
        client.send_event(
            agent,
            "waiting_input",
            {
                "message": WAITING_PROMPTS[index % len(WAITING_PROMPTS)],
            },
        )
        sleep(interval)
        client.send_event(agent, "heartbeat")
        sleep(interval)
        client.send_event(
            agent,
            "command_started",
            {
                "command": "npm run dev",
            },
        )
        sleep(interval)
        client.send_event(
            agent,
            "command_finished",
            {
                "command": "npm run dev",
                "exit_code": 0,
                "duration_ms": 1600,
            },
        )
        sleep(interval)
        client.send_event(agent, "agent_finished")
        return

    if index % 3 == 1:
        client.send_event(
            agent,
            "command_started",
            {
                "command": "pytest",
            },
        )
        sleep(interval)
        client.send_event(
            agent,
            "file_modified",
            {
                "file_path": DEFAULT_FILES[index % len(DEFAULT_FILES)],
                "change_type": "modified",
            },
        )
        sleep(interval)
        client.send_event(
            agent,
            "command_finished",
            {
                "command": "pytest",
                "exit_code": 1,
                "duration_ms": 2350,
            },
        )
        sleep(interval)
        client.send_event(
            agent,
            "agent_failed",
            {
                "reason": "deterministic failure for notification demo",
            },
        )
        return

    client.send_event(
        agent,
        "command_started",
        {
            "command": "pnpm lint",
        },
    )
    sleep(interval)
    client.send_event(
        agent,
        "command_finished",
        {
            "command": "pnpm lint",
            "exit_code": 0,
            "duration_ms": 920,
        },
    )
    sleep(interval)
    client.send_event(agent, "agent_finished")


def sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentBoard mock runner")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="AgentBoard backend base URL")
    parser.add_argument("--agents", type=int, default=3, help="Number of mock agents to simulate")
    parser.add_argument("--project", default="agentboard", help="Project name used in registration payloads")
    parser.add_argument("--interval", type=float, default=0.6, help="Delay between events in seconds")
    parser.add_argument("--cwd", default=str(Path.cwd()), help="Working directory to report for each mock agent")
    parser.add_argument(
        "--scenario",
        default="standard",
        choices=SCENARIO_TYPES,
        help="Event scenario to emit. Use 'attention' to guarantee visible notifications.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payloads instead of posting to the backend")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = BackendClient(args.backend, dry_run=args.dry_run)

    if args.agents < 1:
        print("--agents must be greater than 0", file=sys.stderr)
        return 1

    agents = [make_agent(args.project, args.cwd, index) for index in range(args.agents)]

    print(
        f"Starting mock runner for {len(agents)} agent(s) "
        f"against {args.backend}{' [dry-run]' if args.dry_run else ''}"
    )

    for index, agent in enumerate(agents):
        print(f"- {agent.agent_id} ({agent.agent_type}) {agent.task}")
        try:
            if args.scenario == "attention":
                emit_attention_flow(client, agent, args.interval, index)
            else:
                emit_standard_flow(client, agent, args.interval)
        except RuntimeError as exc:
            print(f"Error while reporting for {agent.agent_id}: {exc}", file=sys.stderr)
            return 1

    print("Mock runner completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
