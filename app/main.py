"""AI Chatbot Engine — FastAPI backend.

RAG-powered chat: OpenAI embeddings + a Postgres-backed knowledge base for
retrieval, OpenAI Responses API for generation, real conversation memory
persisted per session_id.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import schemas
from .chat import get_chat_reply
from .config import config
from .db import Message, get_db, init_db
from .knowledge_base import ensure_seeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

app = FastAPI(title="AI Chatbot Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_request_counts = defaultdict(list)
RATE_LIMIT_PER_MINUTE = 100


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/api/health", "/docs", "/redoc", "/openapi.json"):
        return await call_next(request)

    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=1)
    _request_counts[ip] = [t for t in _request_counts[ip] if t > window_start]
    if len(_request_counts[ip]) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many requests")
    _request_counts[ip].append(now)

    return await call_next(request)


@app.on_event("startup")
async def on_startup():
    db = next(get_db())
    try:
        await ensure_seeded(db)
    finally:
        db.close()


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": config.environment,
    }


@app.post("/api/chat", response_model=schemas.ChatResponse)
async def chat(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    reply = await get_chat_reply(db, payload.session_id, payload.message)
    return schemas.ChatResponse(reply=reply, timestamp=datetime.utcnow().isoformat())


@app.get("/api/conversations/{session_id}", response_model=List[schemas.MessageResponse])
async def get_conversation(session_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )


# ---- Frontend (built React SPA) — registered last so it never shadows /api/* ----
FRONTEND_DIST = (Path(__file__).parent.parent / "frontend_dist").resolve()

if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


def _resolve_frontend_file(rel_path: str) -> Optional[Path]:
    rel_path = rel_path.lstrip("/\\")
    try:
        candidate = (FRONTEND_DIST / rel_path).resolve()
        candidate.relative_to(FRONTEND_DIST)
    except (ValueError, RuntimeError):
        return None
    return candidate


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    candidate = _resolve_frontend_file(full_path)
    if candidate is not None and candidate.is_file():
        return FileResponse(candidate)

    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)

    raise HTTPException(status_code=404, detail="Not found")
