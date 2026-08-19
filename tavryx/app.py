import time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from .config import settings
from .memory import MemoryStore
from .engine import TavryxEngine, command_response
from .models import IncomingMessage

memory = MemoryStore(settings.db_path)
_engine = None
_rate = defaultdict(deque)


def engine():
    global _engine
    if _engine is None:
        _engine = TavryxEngine(memory)
    return _engine


def _authorize(token: str | None):
    if settings.tavryx_api_token and token != settings.tavryx_api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _rate_limit(request: Request):
    # Lightweight guard for the public HTTP surface. Caspian traffic does not
    # pass through this endpoint and is therefore unaffected.
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    q = _rate[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.tavryx_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="TAVRYX rate limit reached. Retry shortly.")
    q.append(now)


def create_app():
    app = FastAPI(
        title="TAVRYX",
        version="3.0.0",
        description="Adaptive situation intelligence: living state, decision evolution, and multi-channel continuity.",
    )

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        with open("static/index.html", encoding="utf-8") as f:
            return f.read()

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "agent": "TAVRYX",
            "version": "3.0.0",
            "environment": settings.app_env,
            "caspian_configured": bool(settings.caspian_api_key),
            "gemini_configured": bool(settings.gemini_api_key),
            "model": settings.gemini_model,
            "memory": "sqlite",
        }

    @app.get("/ready")
    def ready():
        if not settings.gemini_api_key or not settings.caspian_api_key:
            raise HTTPException(status_code=503, detail="Required production secrets are not configured")
        return {"status": "ready", "agent": "TAVRYX", "version": "3.0.0"}

    @app.get("/api/state")
    def state():
        s = memory.latest()
        return {"active": s is not None, "situation": s.model_dump(mode="json") if s else None}

    @app.get("/api/situations")
    def situations():
        return {"items": [s.model_dump(mode="json") for s in memory.list_situations()]}

    @app.get("/api/situations/{situation_id}")
    def situation(situation_id: str):
        s = memory.latest_for(situation_id)
        if not s:
            raise HTTPException(status_code=404, detail="Situation not found")
        timeline = []
        for row in reversed(memory.history_for(situation_id, settings.tavryx_history_per_situation)):
            timeline.append({
                "id": row["id"],
                "at": row["created_at"],
                "channel": row["channel"],
                "input": row["input_text"],
                "situation": row["situation_json"],
            })
        return {"situation": s.model_dump(mode="json"), "timeline": timeline}

    @app.get("/api/radar")
    def radar():
        items = memory.list_situations(12)
        return {
            "agent": "TAVRYX",
            "active_count": sum(1 for s in items if s.lifecycle.value not in {"RESOLVED", "PARKED"}),
            "critical_count": sum(1 for s in items if s.severity == "CRITICAL"),
            "revised_count": sum(1 for s in items if s.decision_revised),
            "items": [s.model_dump(mode="json") for s in items],
        }

    @app.get("/api/memory")
    def memory_endpoint():
        return {"items": memory.recent(settings.tavryx_memory_limit)}

    @app.post("/api/analyze")
    def analyze(request: Request, message: IncomingMessage, x_tavryx_token: str | None = Header(default=None)):
        _authorize(x_tavryx_token)
        _rate_limit(request)
        try:
            result = engine().analyze(message)
            payload = result.model_dump(mode="json")
            # Keep a top-level answer for every successful degradation path as well.
            payload["answer"] = result.situation.answer or result.response
            payload["response"] = result.response
            payload["state"] = result.situation.model_dump(mode="json")
            return payload
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            # The engine is designed to degrade gracefully. This branch is only for
            # programmer/configuration errors that should remain visible to the UI.
            raise HTTPException(status_code=500, detail="TAVRYX encountered an internal processing error. Retry shortly.")

    @app.post("/api/command/{command}")
    def command(request: Request, command, argument: str | None = None, x_tavryx_token: str | None = Header(default=None)):
        _authorize(x_tavryx_token)
        _rate_limit(request)
        result = command_response("/" + command.lstrip("/"), memory, argument)
        if result is None:
            raise HTTPException(status_code=404, detail="Unknown TAVRYX command")
        return {"response": result}

    return app
