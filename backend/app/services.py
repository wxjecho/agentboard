from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


FILE_CHANGE_EVENTS = {"file_created", "file_modified", "file_deleted"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_payload(raw_payload: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def serialize_event(event: models.Event) -> schemas.EventResponse:
    return schemas.EventResponse(
        id=event.id,
        agent_id=event.agent_id,
        event_type=event.event_type,
        payload=parse_payload(event.payload),
        created_at=event.created_at,
    )


def derive_next_status(
    current_status: str,
    event_type: str,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    if event_type == "agent_started":
        return "running", False
    if event_type == "heartbeat":
        return ("blocked", True) if current_status == "blocked" else (current_status or "running", False)
    if event_type == "command_started":
        return "executing", False
    if event_type == "command_finished":
        if payload.get("exit_code") not in (None, 0):
            return "running", True
        return "running", False
    if event_type in FILE_CHANGE_EVENTS:
        return "editing", False
    if event_type == "waiting_input":
        return "waiting_input", True
    if event_type == "agent_failed":
        return "failed", True
    if event_type == "agent_finished":
        return "done", False
    if event_type == "state_changed":
        next_status = str(payload.get("status") or "").strip()
        if next_status:
            return next_status, next_status in {"blocked", "failed", "waiting_input"}
    if event_type == "log" and current_status in {"idle", ""}:
        return "running", False
    return current_status or "running", False


def register_agent(session: Session, payload: schemas.AgentRegisterRequest) -> models.Agent:
    agent = session.get(models.Agent, payload.agent_id)
    timestamp = payload.started_at or utc_now()

    if agent is None:
        agent = models.Agent(
            id=payload.agent_id,
            agent_type=payload.agent_type,
            project=payload.project,
            task=payload.task,
            cwd=payload.cwd,
            source=payload.source,
            status="running",
            started_at=timestamp,
            last_active_at=timestamp,
        )
        session.add(agent)
    else:
        agent.agent_type = payload.agent_type
        agent.project = payload.project
        agent.task = payload.task
        agent.cwd = payload.cwd
        agent.source = payload.source
        agent.status = "running"
        agent.started_at = payload.started_at or agent.started_at or timestamp
        agent.last_active_at = timestamp
        agent.finished_at = None
        agent.needs_intervention = False

    session.commit()
    session.refresh(agent)
    return agent


def ensure_agent_for_event(
    session: Session,
    payload: schemas.EventIngestRequest,
    event_timestamp: datetime,
) -> models.Agent:
    agent = session.get(models.Agent, payload.agent_id)
    if agent is not None:
        return agent

    agent = models.Agent(
        id=payload.agent_id,
        agent_type=payload.agent_type,
        project=payload.project,
        task=payload.task,
        cwd=str(payload.cwd or payload.payload.get("cwd") or payload.project),
        source="auto",
        status="running",
        started_at=event_timestamp,
        last_active_at=event_timestamp,
    )
    session.add(agent)
    session.flush()
    return agent


def ingest_event(session: Session, payload: schemas.EventIngestRequest) -> tuple[models.Agent, models.Event]:
    event_timestamp = payload.timestamp or utc_now()
    agent = ensure_agent_for_event(session, payload, event_timestamp)
    event = models.Event(
        agent_id=payload.agent_id,
        event_type=payload.event_type,
        payload=json.dumps(payload.payload, ensure_ascii=False),
        created_at=event_timestamp,
    )
    session.add(event)

    if payload.event_type in {"command_started", "command_finished"}:
        session.add(
            models.CommandLog(
                agent_id=payload.agent_id,
                command=str(payload.payload.get("command", "")),
                exit_code=payload.payload.get("exit_code"),
                duration_ms=payload.payload.get("duration_ms"),
                created_at=event_timestamp,
            )
        )

    if payload.event_type in FILE_CHANGE_EVENTS:
        session.add(
            models.FileChange(
                agent_id=payload.agent_id,
                file_path=str(payload.payload.get("file_path", "")),
                change_type=str(payload.payload.get("change_type") or payload.event_type.removeprefix("file_")),
                created_at=event_timestamp,
            )
        )

    next_status, needs_intervention = derive_next_status(agent.status, payload.event_type, payload.payload)
    agent.agent_type = payload.agent_type
    agent.project = payload.project
    agent.task = payload.task
    if payload.cwd:
        agent.cwd = payload.cwd
    agent.status = next_status
    agent.last_active_at = event_timestamp
    agent.needs_intervention = agent.needs_intervention or needs_intervention

    if payload.event_type == "command_started":
        agent.current_command = str(payload.payload.get("command", "")).strip() or None
    elif payload.event_type == "command_finished":
        agent.current_command = None

    if payload.event_type == "agent_finished":
        agent.finished_at = event_timestamp
        agent.current_command = None
    elif payload.event_type == "agent_failed":
        agent.finished_at = event_timestamp

    session.commit()
    session.refresh(agent)
    session.refresh(event)
    return agent, event


def list_agents(session: Session) -> list[models.Agent]:
    return list(
        session.scalars(
            select(models.Agent).order_by(models.Agent.updated_at.desc(), models.Agent.created_at.desc())
        )
    )


def get_agent_detail(session: Session, agent_id: str) -> schemas.AgentDetailResponse:
    agent = session.get(models.Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    recent_events = list(
        session.scalars(
            select(models.Event)
            .where(models.Event.agent_id == agent_id)
            .order_by(models.Event.created_at.desc())
            .limit(50)
        )
    )
    recent_command_logs = list(
        session.scalars(
            select(models.CommandLog)
            .where(models.CommandLog.agent_id == agent_id)
            .order_by(models.CommandLog.created_at.desc())
            .limit(50)
        )
    )
    recent_file_changes = list(
        session.scalars(
            select(models.FileChange)
            .where(models.FileChange.agent_id == agent_id)
            .order_by(models.FileChange.created_at.desc())
            .limit(50)
        )
    )

    return schemas.AgentDetailResponse(
        agent=schemas.AgentResponse.model_validate(agent),
        recent_events=[serialize_event(item) for item in recent_events],
        recent_command_logs=[schemas.CommandLogResponse.model_validate(item) for item in recent_command_logs],
        recent_file_changes=[schemas.FileChangeResponse.model_validate(item) for item in recent_file_changes],
    )


def list_recent_important_events(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = list(
        session.scalars(
            select(models.Event)
            .where(
                models.Event.event_type.in_(
                    ["agent_finished", "agent_failed", "waiting_input", "command_finished"]
                )
            )
            .order_by(models.Event.created_at.desc())
            .limit(limit)
        )
    )

    important_events: list[dict[str, Any]] = []
    for event in rows:
        payload = parse_payload(event.payload)
        if event.event_type == "command_finished" and payload.get("exit_code") in (None, 0):
            continue

        agent = session.get(models.Agent, event.agent_id)
        if agent is None:
            continue

        important_events.append(
            {
                "event": serialize_event(event).model_dump(mode="json"),
                "agent": schemas.AgentResponse.model_validate(agent).model_dump(mode="json"),
            }
        )

    return important_events
