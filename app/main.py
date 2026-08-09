"""Nivor Chat Assistant (ai-chatbot-engine) — FastAPI backend.

RAG-powered chat: OpenAI embeddings + a Postgres-backed knowledge base for
retrieval, OpenAI Responses API for generation, real conversation memory.
Real accounts (JWT), real usage metering off persisted Message rows, and
real Stripe subscription billing gate a Free tier against a paid Pro tier.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import billing, schemas, security
from .chat import get_chat_reply
from .config import config
from .db import Message, User, get_db, init_db
from .knowledge_base import ensure_seeded
from .usage import check_within_limit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

app = FastAPI(title="Nivor Chat Assistant", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)

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


# ---- Auth dependencies ----
def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    try:
        payload = security.decode_access_token(credentials.credentials)
    except Exception:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


def get_current_user(current_user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user


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


# ---- Auth ----
@app.post("/api/auth/signup", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=security.hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = security.create_access_token(user.id, user.email)
    return schemas.TokenResponse(access_token=token)


@app.post("/api/auth/login", response_model=schemas.TokenResponse)
async def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = security.create_access_token(user.id, user.email)
    return schemas.TokenResponse(access_token=token)


@app.get("/api/auth/me", response_model=schemas.UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# ---- Usage ----
@app.get("/api/usage", response_model=schemas.UsageResponse)
async def usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, used, limit = check_within_limit(db, current_user)
    return schemas.UsageResponse(plan=current_user.plan, used_this_month=used, limit=limit)


# ---- Chat (anonymous demo chat allowed; tier-gated once signed in) ----
@app.post("/api/chat", response_model=schemas.ChatResponse)
async def chat(
    payload: schemas.ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is not None:
        within_limit, used, limit = check_within_limit(db, current_user)
        if not within_limit:
            return schemas.ChatResponse(
                reply=(
                    f"You've used all {limit} messages on the {current_user.plan} plan this month. "
                    "Upgrade to Pro for a higher limit."
                ),
                timestamp=datetime.utcnow().isoformat(),
                usage_this_month=used,
                usage_limit=limit,
            )

    reply = await get_chat_reply(
        db, payload.session_id, payload.message, user_id=current_user.id if current_user else None
    )

    usage_this_month = usage_limit = None
    if current_user is not None:
        _, usage_this_month, usage_limit = check_within_limit(db, current_user)

    return schemas.ChatResponse(
        reply=reply,
        timestamp=datetime.utcnow().isoformat(),
        usage_this_month=usage_this_month,
        usage_limit=usage_limit,
    )


@app.get("/api/conversations/{session_id}", response_model=List[schemas.MessageResponse])
async def get_conversation(session_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )


# ---- Billing ----
@app.post("/api/billing/checkout", response_model=schemas.CheckoutResponse)
async def billing_checkout(current_user: User = Depends(get_current_user)):
    url = billing.create_checkout_session(current_user)
    return schemas.CheckoutResponse(checkout_url=url)


@app.get("/api/billing/portal", response_model=schemas.PortalResponse)
async def billing_portal(current_user: User = Depends(get_current_user)):
    url = billing.create_portal_session(current_user)
    return schemas.PortalResponse(portal_url=url)


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    return await billing.handle_webhook(request, db)


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
