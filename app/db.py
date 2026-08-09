"""SQLAlchemy engine/session + models. SQLite locally, Postgres (DATABASE_URL) in production.

Embeddings are stored as a portable JSON list[float] column rather than a
Postgres-only `vector` column, so the same schema/code path works identically
on local SQLite and production Postgres — similarity search runs in Python
(numpy) over the small seeded corpus rather than as a SQL operator.

Production Postgres is shared across multiple Nivor apps on the same Railway
project (cost-minimizing — see the deploy plan). Each app therefore gets its
own Postgres *schema* (`chatbot_engine` here) rather than living in the
default `public` schema — otherwise a generic table name like `users` collides
across apps and `create_all()` silently skips the "existing" table, leaving
this app's extra columns missing (this happened once against full-stack-ai-app's
own `public.users` table; fixed by isolating schemas instead of sharing one).
SQLite has no schema concept, so this only applies against Postgres/production.
"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, MetaData, String, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import config

SCHEMA_NAME = "chatbot_engine"
_metadata = MetaData(schema=SCHEMA_NAME) if config.is_production else MetaData()
Base = declarative_base(metadata=_metadata)


class Document(Base):
    """A retrievable knowledge-base chunk with its OpenAI embedding."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=False)  # list[float]
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """A Nivor Chat Assistant account. Free-vs-Pro gating and Stripe state live here."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    plan = Column(String(20), nullable=False, default="free")  # "free" | "pro"
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    """One turn of persisted conversation memory.

    Keyed by client-generated session_id for anonymous/demo chat, and
    additionally by user_id once a visitor is signed in — usage metering and
    tier enforcement only look at rows with a user_id.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


def _database_url() -> str:
    if config.is_production:
        if not config.database_url:
            raise ValueError("DATABASE_URL is required in production")
        return config.database_url
    return config.database_url or "sqlite:///./chatbot_engine.db"


_url = _database_url()
_engine = create_engine(_url, connect_args={"check_same_thread": False} if "sqlite" in _url else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def init_db():
    if config.is_production:
        with _engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
            conn.commit()
    Base.metadata.create_all(bind=_engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
