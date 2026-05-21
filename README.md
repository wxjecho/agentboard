# AgentBoard

AgentBoard is a local-first monitoring platform for AI coding agents. It is designed to collect agent lifecycle events, command execution, file changes, and logs, then present them in a real-time dashboard for developers and teams.

## Scope

This repository starts from the product requirements in `AI Agent Monitor Platform.md` and is organized as a monorepo with three main parts:

- `backend`: API server, persistence layer, and WebSocket event streaming
- `frontend`: real-time dashboard UI
- `runner`: local collector and mock runner prototypes
- `docs`: implementation notes and development plan

## Phase 1 Goal

The first milestone is a local MVP that supports:

- agent registration
- event ingestion
- agent list and detail queries
- WebSocket push updates
- a dashboard overview and detail view
- a mock runner that can continuously emit realistic events

## Planned Stack

- Backend: FastAPI, SQLAlchemy, SQLite, WebSocket
- Frontend: Vue 3, Vite, Tailwind CSS, Pinia
- Runner: Python CLI prototype for mock and future hook integrations

## Repository Layout

```text
agentboard/
  backend/
  frontend/
  runner/
  docs/
```

## Next Steps

1. Scaffold backend service with core models and API routes.
2. Scaffold frontend dashboard with overview and agent detail screens.
3. Add a mock runner to simulate multi-agent activity locally.
4. Wire WebSocket updates from backend to frontend.
5. Add Claude Code hook integration after the MVP loop is stable.
