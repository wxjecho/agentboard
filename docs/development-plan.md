# Development Plan

## Objective

Build a local-first MVP of AgentBoard that can monitor multiple AI agents in real time and provide a path to production-oriented integrations later.

## Milestone 1: Local MVP

### Backend

- create FastAPI app entrypoint
- define agent and event schemas
- implement SQLite persistence
- implement `POST /api/agents/register`
- implement `POST /api/events`
- implement `GET /api/agents`
- implement `GET /api/agents/{id}`
- implement `/ws/agents`

### Frontend

- create Vue 3 app with Vite
- add dashboard shell and routing
- build agent overview page
- build agent detail page or drawer
- subscribe to WebSocket stream

### Runner

- create mock runner CLI
- emit lifecycle, log, command, and file events
- simulate heartbeat and completion flows

## Milestone 2: Real Integrations

- map Claude Code hooks to internal events
- add intervention markers and stuck-agent heuristics
- add notifications
- prepare adapter boundaries for Codex, cc, Gemini CLI, and others

## Notes

- Redis is optional in the first milestone and can be added after the local real-time flow is stable.
- SQLite is sufficient for the first closed-loop version.
- The backend event model should stay generic enough to support multiple agent vendors.
