from __future__ import annotations

import argparse
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

from workspace_watcher import start_workspace_watcher


DEFAULT_BACKEND = "http://127.0.0.1:8000"
DEFAULT_HEARTBEAT_INTERVAL = 8.0
DEFAULT_WATCH_INTERVAL = 1.0
BLOCKED_MARKERS = (
    "stream disconnected - retrying sampling request",
    "reconnecting...",
    "timeout waiting for child process to exit",
)


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
            "source": "runner",
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


def make_session(project: str, task: str, cwd: str) -> AgentSession:
    return AgentSession(
        agent_id=f"codex-{uuid.uuid4().hex[:10]}",
        agent_type="codex",
        project=project,
        task=task,
        cwd=cwd,
    )


def start_heartbeat(
    client: BackendClient,
    session: AgentSession,
    stop_event: threading.Event,
    interval: float,
) -> threading.Thread:
    def emit_heartbeat() -> None:
        while not stop_event.wait(interval):
            try:
                client.send_event(session, "heartbeat")
            except RuntimeError as exc:
                print(f"Heartbeat failed for {session.agent_id}: {exc}", file=sys.stderr)
                break

    thread = threading.Thread(target=emit_heartbeat, name=f"{session.agent_id}-heartbeat", daemon=True)
    thread.start()
    return thread


def start_file_watcher(
    client: BackendClient,
    session: AgentSession,
    stop_event: threading.Event,
    interval: float,
) -> threading.Thread:
    def emit_file_event(event_type: str, file_path: str) -> None:
        try:
            client.send_event(
                session,
                event_type,
                {
                    "file_path": file_path,
                    "change_type": event_type.removeprefix("file_"),
                },
            )
        except RuntimeError as exc:
            print(f"File watcher failed for {session.agent_id}: {exc}", file=sys.stderr)

    return start_workspace_watcher(
        root=session.cwd,
        on_event=emit_file_event,
        stop_event=stop_event,
        interval=interval,
    )


def reader_thread(stream: Any, name: str, lines: queue.Queue[tuple[str, str]]) -> threading.Thread:
    def consume() -> None:
        try:
            for raw_line in iter(stream.readline, ""):
                line = raw_line.rstrip("\n")
                if line:
                    lines.put((name, line))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    thread = threading.Thread(target=consume, name=f"reader-{name}", daemon=True)
    thread.start()
    return thread


def maybe_parse_json_line(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_log_payload(stream_name: str, line: str) -> dict[str, Any]:
    parsed = maybe_parse_json_line(line)
    if not parsed:
        return {
            "stream": stream_name,
            "content": line,
        }

    event_type = str(parsed.get("type") or parsed.get("event") or "json")
    summary = ""
    if isinstance(parsed.get("msg"), str):
        summary = parsed["msg"]
    elif isinstance(parsed.get("message"), str):
        summary = parsed["message"]
    elif isinstance(parsed.get("content"), str):
        summary = parsed["content"]
    else:
        summary = event_type

    return {
        "stream": stream_name,
        "content": summary,
        "raw": parsed,
    }


def extract_log_summary(line: str) -> str:
    parsed = maybe_parse_json_line(line)
    if not parsed:
        return line

    if isinstance(parsed.get("msg"), str):
        return parsed["msg"]
    if isinstance(parsed.get("message"), str):
        return parsed["message"]
    if isinstance(parsed.get("content"), str):
        return parsed["content"]
    if isinstance(parsed.get("type"), str):
        return parsed["type"]
    return line


def is_blocked_signal(summary: str) -> bool:
    lowered = summary.lower()
    return any(marker in lowered for marker in BLOCKED_MARKERS)


def emit_stream_logs(
    client: BackendClient,
    session: AgentSession,
    process: subprocess.Popen[str],
    command_label: str,
) -> None:
    lines: queue.Queue[tuple[str, str]] = queue.Queue()
    stdout_thread = reader_thread(process.stdout, "stdout", lines) if process.stdout else None
    stderr_thread = reader_thread(process.stderr, "stderr", lines) if process.stderr else None
    blocked_active = False

    while True:
        alive_readers = any(thread and thread.is_alive() for thread in (stdout_thread, stderr_thread))
        try:
            stream_name, line = lines.get(timeout=0.2)
            log_payload = build_log_payload(stream_name, line)
            client.send_event(session, "log", log_payload)
            maybe_emit_waiting_input(client, session, line)
            summary = extract_log_summary(line)

            if is_blocked_signal(summary):
                if not blocked_active:
                    client.send_event(
                        session,
                        "state_changed",
                        {
                            "status": "blocked",
                            "reason": summary,
                        },
                    )
                    blocked_active = True
            elif blocked_active and stream_name == "stdout":
                client.send_event(
                    session,
                    "state_changed",
                    {
                        "status": "executing",
                        "reason": "Codex output resumed after blocked state",
                    },
                )
                blocked_active = False
        except queue.Empty:
            if process.poll() is not None and not alive_readers and lines.empty():
                break

    for thread in (stdout_thread, stderr_thread):
        if thread:
            thread.join(timeout=0.5)

    client.send_event(
        session,
        "log",
        {
            "stream": "stdout",
            "content": f"Codex command completed: {command_label}",
        },
    )


def maybe_emit_waiting_input(client: BackendClient, session: AgentSession, line: str) -> None:
    lowered = line.lower()
    markers = [
        "approval",
        "waiting for user",
        "need your input",
        "awaiting user",
        "confirm",
    ]
    if any(marker in lowered for marker in markers):
        client.send_event(
            session,
            "waiting_input",
            {
                "message": line,
            },
        )


def build_codex_command(args: argparse.Namespace) -> list[str]:
    command = ["codex"]

    if args.ask_for_approval:
        command.extend(["--ask-for-approval", args.ask_for_approval])

    command.extend(
        [
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--cd",
            args.cwd,
        ]
    )

    if args.model:
        command.extend(["--model", args.model])
    if args.profile:
        command.extend(["--profile", args.profile])
    if args.sandbox:
        command.extend(["--sandbox", args.sandbox])
    if args.dangerously_bypass_approvals_and_sandbox:
        command.append("--dangerously-bypass-approvals-and-sandbox")

    command.append(args.prompt)
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Codex through AgentBoard and report events")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="AgentBoard backend base URL")
    parser.add_argument("--project", default="agentboard", help="Project name shown in AgentBoard")
    parser.add_argument("--task", required=True, help="Human-readable task title for the Agent session")
    parser.add_argument("--prompt", required=True, help="Prompt passed to `codex exec`")
    parser.add_argument("--cwd", default=str(Path.cwd()), help="Working directory for Codex")
    parser.add_argument("--model", default="", help="Optional model name passed to Codex")
    parser.add_argument("--profile", default="", help="Optional Codex config profile")
    parser.add_argument(
        "--sandbox",
        default="workspace-write",
        choices=["read-only", "workspace-write", "danger-full-access"],
        help="Sandbox mode forwarded to Codex",
    )
    parser.add_argument(
        "--ask-for-approval",
        default="never",
        choices=["untrusted", "on-failure", "on-request", "never"],
        help="Approval policy forwarded to Codex exec",
    )
    parser.add_argument(
        "--dangerously-bypass-approvals-and-sandbox",
        action="store_true",
        help="Forward Codex's no-approval/no-sandbox mode",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=DEFAULT_HEARTBEAT_INTERVAL,
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=DEFAULT_WATCH_INTERVAL,
        help="Workspace polling interval in seconds for file change reporting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print backend payloads while still running the local codex command",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the generated codex command before execution",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Print the generated command and exit without launching Codex",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cwd = os.path.abspath(args.cwd)
    session = make_session(project=args.project, task=args.task, cwd=cwd)
    client = BackendClient(args.backend, dry_run=args.dry_run)
    command = build_codex_command(args)
    command_label = shlex.join(command)

    if args.print_command:
        print(command_label)

    if args.preview_only:
        print("Preview only; Codex process was not started.")
        return 0

    print(f"Starting Codex runner for {session.agent_id}")
    print(f"- project: {session.project}")
    print(f"- task: {session.task}")
    print(f"- cwd: {session.cwd}")

    start_time = time.monotonic()
    stop_event = threading.Event()

    try:
        client.register_agent(session)
        client.send_event(session, "agent_started")
        client.send_event(
            session,
            "command_started",
            {
                "command": command_label,
            },
        )

        heartbeat_thread = start_heartbeat(client, session, stop_event, args.heartbeat_interval)
        watcher_thread = start_file_watcher(client, session, stop_event, args.watch_interval)

        process = subprocess.Popen(
            command,
            cwd=session.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        emit_stream_logs(client, session, process, command_label)
        exit_code = process.wait()
        duration_ms = int((time.monotonic() - start_time) * 1000)

        client.send_event(
            session,
            "command_finished",
            {
                "command": command_label,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )

        if exit_code == 0:
            client.send_event(session, "agent_finished")
        else:
            client.send_event(
                session,
                "agent_failed",
                {
                    "reason": f"codex exited with status {exit_code}",
                },
            )

        stop_event.set()
        heartbeat_thread.join(timeout=1)
        watcher_thread.join(timeout=1)

        print(f"Codex runner completed with exit code {exit_code}")
        return exit_code
    except FileNotFoundError:
        print("Could not find `codex` in PATH.", file=sys.stderr)
        return 127
    except RuntimeError as exc:
        stop_event.set()
        print(f"Runner failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
