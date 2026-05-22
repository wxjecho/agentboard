from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import Base, engine, get_db_session
from .schemas import AgentCollectionResponse, AgentRegisterRequest, AgentResponse, EventIngestRequest
from .services import (
    get_agent_detail,
    ingest_event,
    list_agents,
    list_recent_important_events,
    register_agent,
    serialize_event,
)
from .websocket_manager import manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AgentBoard API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/agents/register", response_model=AgentResponse)
async def register_agent_endpoint(
    payload: AgentRegisterRequest,
    session: Session = Depends(get_db_session),
) -> AgentResponse:
    agent = register_agent(session, payload)
    response = AgentResponse.model_validate(agent)
    await manager.broadcast({"type": "agent_registered", "agent": response.model_dump(mode="json")})
    return response


@app.post("/api/events")
async def ingest_event_endpoint(
    payload: EventIngestRequest,
    session: Session = Depends(get_db_session),
) -> dict[str, object]:
    agent, event = ingest_event(session, payload)
    agent_response = AgentResponse.model_validate(agent)
    event_response = serialize_event(event)
    await manager.broadcast(
        {
            "type": "event_ingested",
            "agent": agent_response.model_dump(mode="json"),
            "event": event_response.model_dump(mode="json"),
        }
    )
    return {
        "ok": True,
        "agent": agent_response.model_dump(mode="json"),
        "event": event_response.model_dump(mode="json"),
    }


@app.get("/api/agents", response_model=AgentCollectionResponse)
def list_agents_endpoint(session: Session = Depends(get_db_session)) -> AgentCollectionResponse:
    agents = [AgentResponse.model_validate(item) for item in list_agents(session)]
    return AgentCollectionResponse(items=agents, total=len(agents))


@app.get("/api/agents/{agent_id}")
def agent_detail_endpoint(agent_id: str, session: Session = Depends(get_db_session)) -> dict[str, object]:
    detail = get_agent_detail(session, agent_id)
    return detail.model_dump(mode="json")


@app.get("/api/events/recent")
def recent_events_endpoint(limit: int = 20, session: Session = Depends(get_db_session)) -> dict[str, object]:
    events = list_recent_important_events(session, limit=limit)
    return {"items": events, "total": len(events)}


@app.websocket("/ws/agents")
async def agents_websocket(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "connected", "channel": "agents"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
