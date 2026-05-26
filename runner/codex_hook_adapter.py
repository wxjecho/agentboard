from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


DEFAULT_BACKEND = "http://127.0.0.1:8000"
STATE_FILE = Path("/private/tmp/agentboard_codex_sessions.json")
MAX_TASK_LENGTH = 120


@dataclass
class AgentSession:
    agent_id: str
    agent_type: str
    project: str
    task: str
    cwd: str


class BackendClient:
    def __init__(self, backend: str, dry_run: bool = False) -> None:
        self.backend = backend.rstrip("/")
        self.dry_run = dry_run

    def register_agent(self, session: AgentSession) -> None:
        payload = {
            "agent_id": session.agent_id,
            "agent_type": session.agent_type,
            "project": session.project,
            "task": session.task,
            "cwd": session.cwd,
            "source": "codex-hook",
            "started_at": iso_now(),
        }
        self._post("/api/agents/register", payload)

    def send_event(
        self,
        session: AgentSession,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        body = {
            "agent_id": session.agent_id,
            "agent_type": session.agent_type,
            "project": session.project,
            "task": session.task,
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


def load_state() -> dict[str, dict[str, Any]]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, dict[str, Any]]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def summarize_task(text: str) -> str:
    single_line = re.sub(r"\s+", " ", text).strip()
    if not single_line:
        return "Codex session"
    return single_line[:MAX_TASK_LENGTH]


def build_agent_id(session_id: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9]", "", session_id)
    return f"codex-{sanitized[:10] or uuid.uuid4().hex[:10]}"


def infer_project(args_project: str, cwd: str) -> str:
    if args_project:
        return args_project
    return Path(cwd).name or "project"


def extract_session_id(payload: dict[str, Any]) -> str:
    session_id = str(payload.get("session_id") or "").strip()
    if session_id:
        return session_id

    if isinstance(payload.get("session"), dict):
        nested = str(payload["session"].get("id") or "").strip()
        if nested:
            return nested

    return uuid.uuid4().hex


def ensure_session_record(
    state: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    args_project: str,
) -> tuple[AgentSession, bool]:
    session_id = extract_session_id(payload)
    cwd = str(payload.get("cwd") or os.getcwd())
    existing = state.get(session_id)

    if existing is None:
        prompt = extract_prompt(payload)
        task = summarize_task(prompt or "Codex session")
        session = AgentSession(
            agent_id=build_agent_id(session_id),
            agent_type="codex",
            project=infer_project(args_project, cwd),
            task=task,
            cwd=cwd,
        )
        state[session_id] = {
            "agent_id": session.agent_id,
            "project": session.project,
            "task": session.task,
            "cwd": session.cwd,
        }
        return session, True

    prompt = extract_prompt(payload)
    if prompt:
        existing["task"] = summarize_task(prompt)
    existing["cwd"] = cwd
    if args_project:
        existing["project"] = args_project

    session = AgentSession(
        agent_id=str(existing["agent_id"]),
        agent_type="codex",
        project=str(existing.get("project") or infer_project(args_project, cwd)),
        task=str(existing.get("task") or "Codex session"),
        cwd=str(existing.get("cwd") or cwd),
    )
    return session, False


def extract_prompt(payload: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "tool"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def extract_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_input", "input"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def extract_tool_response(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_response", "output", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def extract_command(tool_input: dict[str, Any]) -> str:
    for key in ("command", "cmd"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_exit_code(payload: dict[str, Any], tool_response: dict[str, Any], default: int = 0) -> int:
    for source in (tool_response, payload):
        for key in ("exit_code", "exitCode", "status", "code"):
            value = source.get(key)
            if isinstance(value, int):
                return value
    return default


def extract_duration_ms(payload: dict[str, Any], tool_response: dict[str, Any]) -> int | None:
    for source in (tool_response, payload):
        for key in ("duration_ms", "durationMs"):
            value = source.get(key)
            if isinstance(value, int):
                return value
    return None


def emit_log(client: BackendClient, session: AgentSession, message: str, stream: str = "stdout") -> None:
    client.send_event(
        session,
        "log",
        {
            "stream": stream,
            "content": message,
        },
    )


def maybe_emit_file_change(
    client: BackendClient,
    session: AgentSession,
    tool_name: str,
    tool_input: dict[str, Any],
) -> None:
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "").strip()
    if not file_path:
        return

    if tool_name == "Write":
        client.send_event(session, "file_created", {"file_path": file_path, "change_type": "created"})
    elif tool_name in {"Edit", "MultiEdit", "NotebookEdit"}:
        client.send_event(session, "file_modified", {"file_path": file_path, "change_type": "modified"})


def ensure_registered(client: BackendClient, session: AgentSession, created: bool) -> None:
    if created:
        client.register_agent(session)
        client.send_event(session, "agent_started")


def handle_session_start(client: BackendClient, session: AgentSession, payload: dict[str, Any], created: bool) -> None:
    ensure_registered(client, session, created)
    source = str(payload.get("source") or "unknown")
    model = str(payload.get("model") or "unknown")
    emit_log(client, session, f"Codex session started via {source} on model {model}")
    client.send_event(
        session,
        "state_changed",
        {
            "status": "running",
            "reason": "Codex interactive session is active",
        },
    )


def handle_user_prompt_submit(
    client: BackendClient,
    session: AgentSession,
    payload: dict[str, Any],
    created: bool,
) -> None:
    ensure_registered(client, session, created)
    prompt = extract_prompt(payload)
    if prompt:
        emit_log(client, session, f"User prompt submitted: {summarize_task(prompt)}")
    client.send_event(
        session,
        "state_changed",
        {
            "status": "running",
            "reason": "Waiting for Codex to respond",
        },
    )


def handle_pre_tool_use(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    tool_name = extract_tool_name(payload)
    tool_input = extract_tool_input(payload)

    if tool_name == "Bash":
        client.send_event(
            session,
            "command_started",
            {
                "command": extract_command(tool_input),
            },
        )
        return

    if tool_name in {"Edit", "MultiEdit", "NotebookEdit", "Write"}:
        client.send_event(
            session,
            "state_changed",
            {
                "status": "editing",
                "reason": f"Codex is using {tool_name}",
            },
        )
        return

    emit_log(client, session, f"PreToolUse: {tool_name}")


def handle_post_tool_use(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    tool_name = extract_tool_name(payload)
    tool_input = extract_tool_input(payload)
    tool_response = extract_tool_response(payload)

    if tool_name == "Bash":
        client.send_event(
            session,
            "command_finished",
            {
                "command": extract_command(tool_input),
                "exit_code": extract_exit_code(payload, tool_response, default=0),
                "duration_ms": extract_duration_ms(payload, tool_response),
            },
        )
        return

    maybe_emit_file_change(client, session, tool_name, tool_input)
    emit_log(client, session, f"PostToolUse: {tool_name}")


def handle_permission_request(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    tool_name = extract_tool_name(payload)
    tool_input = extract_tool_input(payload)
    message = str(payload.get("message") or "").strip()
    command = extract_command(tool_input)
    prompt = message or command or f"Codex requests permission for {tool_name or 'a tool'}"
    client.send_event(
        session,
        "waiting_input",
        {
            "message": prompt,
        },
    )


def handle_stop(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    last_message = str(payload.get("last_assistant_message") or payload.get("response") or "").strip()
    if last_message:
        emit_log(client, session, f"Codex final response: {summarize_task(last_message)}")
    client.send_event(
        session,
        "state_changed",
        {
            "status": "idle",
            "reason": "Codex is waiting for the next user prompt",
        },
    )


def handle_hook_event(
    client: BackendClient,
    state: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    args_project: str,
) -> None:
    session, created = ensure_session_record(state, payload, args_project)
    event_name = str(payload.get("hook_event_name") or "")

    if event_name == "SessionStart":
        handle_session_start(client, session, payload, created)
    elif event_name == "UserPromptSubmit":
        handle_user_prompt_submit(client, session, payload, created)
    elif event_name == "PreToolUse":
        handle_pre_tool_use(client, session, payload)
    elif event_name == "PostToolUse":
        handle_post_tool_use(client, session, payload)
    elif event_name == "PermissionRequest":
        handle_permission_request(client, session, payload)
    elif event_name == "Stop":
        handle_stop(client, session, payload)
    else:
        emit_log(client, session, f"Unhandled Codex hook event: {event_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Codex hooks into AgentBoard")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="AgentBoard backend base URL")
    parser.add_argument("--project", default="", help="Optional project label override")
    parser.add_argument("--dry-run", action="store_true", help="Print backend payloads without sending them")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"Invalid Codex hook payload: {exc}", file=sys.stderr)
        return 1

    state = load_state()
    client = BackendClient(args.backend, dry_run=args.dry_run)

    try:
        handle_hook_event(client, state, payload, args.project)
        save_state(state)
        if not args.dry_run and str(payload.get("hook_event_name") or "") == "Stop":
            print("{}")
        return 0
    except RuntimeError as exc:
        print(f"Codex hook adapter failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
