from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentRegisterRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    agent_type: str = Field(min_length=1, max_length=64)
    project: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=1)
    cwd: str = Field(min_length=1)
    source: str = Field(default="runner", min_length=1, max_length=32)
    started_at: Optional[datetime] = None


class EventIngestRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    agent_type: str = Field(min_length=1, max_length=64)
    project: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=1)
    event_type: str = Field(min_length=1, max_length=64)
    timestamp: Optional[datetime] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_type: str
    project: str
    task: str
    cwd: str
    source: str
    status: str
    current_command: Optional[str]
    needs_intervention: bool
    started_at: Optional[datetime]
    last_active_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class EventResponse(BaseModel):
    id: int
    agent_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: Optional[datetime]


class CommandLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    command: str
    exit_code: Optional[int]
    duration_ms: Optional[int]
    created_at: Optional[datetime]


class FileChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    file_path: str
    change_type: str
    created_at: Optional[datetime]


class AgentDetailResponse(BaseModel):
    agent: AgentResponse
    recent_events: list[EventResponse]
    recent_command_logs: list[CommandLogResponse]
    recent_file_changes: list[FileChangeResponse]


class AgentCollectionResponse(BaseModel):
    items: list[AgentResponse]
    total: int
