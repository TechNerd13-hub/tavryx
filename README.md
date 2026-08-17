# TAVRYX 3.0 — Adaptive Situation Intelligence

**TAVRYX does not treat every message as a new conversation. It maintains living situations.**

A message becomes a structured situation with a durable ID, lifecycle, trajectory, evidence, recommendation and state delta. New evidence can continue the same situation, revise a decision, resolve it, park it, or open a new situation. Caspian gives the same agent identity across connected communication channels.

## Production profile

- **Gemini 3.6 Flash** for strong agentic reasoning.
- **Adaptive thinking budget:** low for normal traffic, medium for complex/critical situations.
- **Structured JSON output** validated with Pydantic.
- **Bounded recovery retry** on model failures.
- **Graceful Discord/email failure message** that never exposes stack traces.
- **Persistent SQLite situation memory.**
- **Situation portfolio selection:** new signals can resume older relevant situations instead of being forced into the globally latest thread.
- **Situation radar + timeline dashboard** for live state visibility.
- **Rate-limited HTTP mutation surface** and readiness endpoint.
- **Caspian one-handler multi-channel architecture.**
- FastAPI health/API surface and Docker/Render deployment files.
- Optional `TAVRYX_API_TOKEN` for protecting HTTP mutation endpoints.
- Offline test suite with no API calls.

## The differentiator

Most assistants optimize for the current message. TAVRYX optimizes for **what changed in the situation**.

`SIGNAL → SITUATION → STATE DELTA → DECISION → ACTION/APPROVAL → VERIFICATION → EVOLUTION`

The same model can switch between INCIDENT, DECISION, LEARNING, CREATIVE, PLANNING and GENERAL modes without hard-coded domain bots.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set:

```text
GEMINI_API_KEY=...
CASPIAN_API_KEY=...
CASPIAN_BASE_URL=https://api.trycaspianai.com
```

Run the complete local release gate in one command:

```bash
./release_check.sh
```

It installs the locked requirements, runs the full offline test suite, compiles the project, and verifies that `GEMINI_API_KEY` and `CASPIAN_API_KEY` are present.

Run the production-shaped local process:

```bash
python main.py
```

## Caspian

Caspian uses one `on_message` handler for connected channels. Connect Discord/email/etc. with the Caspian CLI and keep the same TAVRYX process running.

## Commands

- `/focus` — highest-leverage next move
- `/brief` — compact current situation
- `/why` — explain the latest state movement
- `/state` — current adaptive state
- `/memory` — recent stored events
- `/timeline [S-XXXXXXXX]` — evolution timeline for a situation
- `/situations` — active situation threads
- `/park S-XXXXXXXX` — park a situation
- `/resume S-XXXXXXXX` — resume it
- `/reset` — clear local situation memory

## Deployment

Docker:

```bash
docker build -t tavryx .
docker run --env-file .env -p 8000:8000 tavryx
```

Render is configured in `render.yaml`. Add `GEMINI_API_KEY` and `CASPIAN_API_KEY` as secrets. If the service is public, set `TAVRYX_API_TOKEN` to protect the HTTP mutation endpoints.

## API

- `GET /` — dashboard
- `GET /health` — health/config status
- `GET /api/state` — current situation
- `GET /api/situations` — situation list
- `GET /api/situations/{id}` — one situation
- `GET /api/memory` — recent event memory
- `POST /api/analyze` — analyze a new message
- `POST /api/command/{command}` — run a TAVRYX command

## Security

Never commit `.env` or API keys. TAVRYX never treats model text as permission to execute arbitrary external actions. Any future side-effecting tools should be explicit allowlisted functions with authentication, audit logging and human approval where appropriate.
