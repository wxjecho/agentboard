from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


DEFAULT_BACKEND = "http://127.0.0.1:8000"
STATE_FILE = Path(tempfile.gettempdir()) / "agentboard_claude_sessions.json"
MAX_TASK_LENGTH = 120
HOOK_EVENT_NAMES = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "Stop",
    "SessionEnd",
]


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
            "source": "claude-hook",
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
            "cwd": session.cwd,
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
    except OSError as exc:
        print(f"Could not persist Claude hook state to {STATE_FILE}: {exc}", file=sys.stderr)


def load_stdin_json() -> dict[str, Any] | None:
    chunks: list[bytes] = []
    while True:
        data = os.read(0, 65536)
        if not data:
            break
        chunks.append(data)

    if not chunks:
        return None

    raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def build_hooks_config(command: str) -> dict[str, Any]:
    command_hook = {"type": "command", "command": command}
    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [command_hook],
                }
            ],
            "UserPromptSubmit": [{"hooks": [command_hook]}],
            "PreToolUse": [
                {
                    "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [command_hook],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [command_hook],
                }
            ],
            "PostToolUseFailure": [
                {
                    "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [command_hook],
                }
            ],
            "Notification": [{"hooks": [command_hook]}],
            "Stop": [{"hooks": [command_hook]}],
            "SessionEnd": [
                {
                    "matcher": "clear|resume|logout|prompt_input_exit|other",
                    "hooks": [command_hook],
                }
            ],
        }
    }


def install_hooks(settings_path: Path, backend: str) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read existing settings.json: {exc}") from exc
        if not isinstance(settings, dict):
            raise RuntimeError("Existing settings.json must contain a JSON object")
    else:
        settings = {}

    hooks = settings.get("hooks")
    if hooks is None:
        hooks = {}
        settings["hooks"] = hooks
    elif not isinstance(hooks, dict):
        raise RuntimeError("Existing settings.json has a non-object 'hooks' field")

    command = f'python3 "{Path(__file__).resolve()}" --backend {backend}'
    generated = build_hooks_config(command)["hooks"]
    for event_name in HOOK_EVENT_NAMES:
        hooks[event_name] = generated[event_name]

    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_task(prompt: str) -> str:
    single_line = re.sub(r"\s+", " ", prompt).strip()
    if not single_line:
        return "Claude Code session"
    return single_line[:MAX_TASK_LENGTH]


def build_agent_id(session_id: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9]", "", session_id)
    return f"claude-code-{sanitized[:10] or uuid.uuid4().hex[:10]}"


def infer_project(args_project: str, cwd: str) -> str:
    if args_project:
        return args_project
    return Path(cwd).name or "project"


def ensure_session_record(
    state: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    args_project: str,
) -> tuple[AgentSession, bool]:
    session_id = str(payload.get("session_id") or uuid.uuid4().hex)
    cwd = str(payload.get("cwd") or os.getcwd())
    existing = state.get(session_id)

    if existing is None:
        task = summarize_task(str(payload.get("prompt") or "Claude Code session"))
        session = AgentSession(
            agent_id=build_agent_id(session_id),
            agent_type="claude-code",
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

    if payload.get("prompt"):
        existing["task"] = summarize_task(str(payload["prompt"]))
    existing["cwd"] = cwd
    if args_project:
        existing["project"] = args_project

    session = AgentSession(
        agent_id=str(existing["agent_id"]),
        agent_type="claude-code",
        project=str(existing.get("project") or infer_project(args_project, cwd)),
        task=str(existing.get("task") or "Claude Code session"),
        cwd=str(existing.get("cwd") or cwd),
    )
    return session, False


def delete_session_record(state: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    session_id = str(payload.get("session_id") or "")
    if session_id in state:
        del state[session_id]


def extract_tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("tool_name") or "")


def extract_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    tool_input = payload.get("tool_input")
    return tool_input if isinstance(tool_input, dict) else {}


def extract_tool_response(payload: dict[str, Any]) -> dict[str, Any]:
    tool_response = payload.get("tool_response")
    return tool_response if isinstance(tool_response, dict) else {}


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


def handle_session_start(client: BackendClient, session: AgentSession, payload: dict[str, Any], created: bool) -> None:
    if created:
        client.register_agent(session)
        client.send_event(session, "agent_started")
    emit_log(
        client,
        session,
        f"Claude session started via {payload.get('source', 'unknown')} on model {payload.get('model', 'unknown')}",
    )


def handle_user_prompt_submit(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    prompt = str(payload.get("prompt") or "").strip()
    if prompt:
        emit_log(client, session, f"User prompt submitted: {summarize_task(prompt)}")


def handle_pre_tool_use(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    tool_name = extract_tool_name(payload)
    tool_input = extract_tool_input(payload)

    if tool_name == "Bash":
        client.send_event(
            session,
            "command_started",
            {
                "command": str(tool_input.get("command") or ""),
            },
        )
        return

    if tool_name in {"Edit", "MultiEdit", "NotebookEdit", "Write"}:
        client.send_event(
            session,
            "state_changed",
            {
                "status": "editing",
                "reason": f"Claude is using {tool_name}",
            },
        )
        return

    emit_log(client, session, f"PreToolUse: {tool_name}")


def handle_post_tool_use(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    tool_name = extract_tool_name(payload)
    tool_input = extract_tool_input(payload)
    tool_response = extract_tool_response(payload)

    if tool_name == "Bash":
        exit_code = tool_response.get("exit_code", 0)
        duration_ms = tool_response.get("duration_ms")
        client.send_event(
            session,
            "command_finished",
            {
                "command": str(tool_input.get("command") or ""),
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )
        return

    maybe_emit_file_change(client, session, tool_name, tool_input)
    emit_log(client, session, f"PostToolUse: {tool_name}")


def handle_post_tool_use_failure(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    tool_name = extract_tool_name(payload)
    tool_input = extract_tool_input(payload)
    tool_response = extract_tool_response(payload)
    message = ""
    if isinstance(tool_response.get("error"), str):
        message = tool_response["error"]
    elif isinstance(payload.get("error"), str):
        message = str(payload["error"])
    else:
        message = f"{tool_name} failed"

    if tool_name == "Bash":
        client.send_event(
            session,
            "command_finished",
            {
                "command": str(tool_input.get("command") or ""),
                "exit_code": tool_response.get("exit_code", 1),
                "duration_ms": tool_response.get("duration_ms"),
            },
        )
    emit_log(client, session, message, stream="stderr")
    client.send_event(
        session,
        "state_changed",
        {
            "status": "blocked",
            "reason": message,
        },
    )


def handle_notification(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    message = str(payload.get("message") or "").strip()
    title = str(payload.get("title") or "").strip()
    notification_type = str(payload.get("notification_type") or "").strip()

    if notification_type in {"permission_prompt", "idle_prompt", "elicitation_dialog", "elicitation_complete"}:
        client.send_event(
            session,
            "waiting_input",
            {
                "message": message or title or notification_type,
            },
        )
        return

    emit_log(client, session, f"Notification[{notification_type or 'generic'}]: {title or message}")


def handle_stop(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    last_message = str(payload.get("last_assistant_message") or "").strip()
    if last_message:
        emit_log(client, session, f"Claude final response: {summarize_task(last_message)}")
    client.send_event(session, "agent_finished")


def handle_session_end(client: BackendClient, session: AgentSession, payload: dict[str, Any]) -> None:
    reason = str(payload.get("reason") or "other")
    emit_log(client, session, f"Claude session ended: {reason}")


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
        if created:
            client.register_agent(session)
            client.send_event(session, "agent_started")
        handle_user_prompt_submit(client, session, payload)
    elif event_name == "PreToolUse":
        handle_pre_tool_use(client, session, payload)
    elif event_name == "PostToolUse":
        handle_post_tool_use(client, session, payload)
    elif event_name == "PostToolUseFailure":
        handle_post_tool_use_failure(client, session, payload)
    elif event_name == "Notification":
        handle_notification(client, session, payload)
    elif event_name == "Stop":
        handle_stop(client, session, payload)
    elif event_name == "SessionEnd":
        handle_session_end(client, session, payload)
        delete_session_record(state, payload)
    else:
        emit_log(client, session, f"Unhandled Claude hook event: {event_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Claude Code hooks into AgentBoard")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="AgentBoard backend base URL")
    parser.add_argument("--project", default="", help="Optional project label override")
    parser.add_argument("--dry-run", action="store_true", help="Print backend payloads without sending them")
    parser.add_argument("--install", action="store_true", help="Install Claude hooks into a settings.json file")
    parser.add_argument(
        "--settings-path",
        default="",
        help="Optional settings.json target path used with --install (default: .claude/settings.json in cwd)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.install:
        settings_path = Path(args.settings_path).expanduser() if args.settings_path else Path.cwd() / ".claude" / "settings.json"
        try:
            install_hooks(settings_path, args.backend)
            print(f"Installed Claude hooks into {settings_path}")
            return 0
        except RuntimeError as exc:
            print(f"Claude hook install failed: {exc}", file=sys.stderr)
            return 1

    payload = load_stdin_json()
    if payload is None:
        return 0

    state = load_state()
    client = BackendClient(args.backend, dry_run=args.dry_run)

    try:
        handle_hook_event(client, state, payload, args.project)
        save_state(state)
        return 0
    except RuntimeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
