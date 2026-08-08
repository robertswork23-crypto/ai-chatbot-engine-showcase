"""Seed knowledge base for the RAG demo — a small set of FAQ-style chunks
about this product itself, embedded once at startup if the documents table
is empty. Real retrieval over a real (if small) corpus, not a hardcoded
lookup table.
"""
import logging
from typing import List

from sqlalchemy.orm import Session

from .db import Document
from .embeddings import embed_text

logger = logging.getLogger(__name__)

SEED_DOCS: List[str] = [
    "This is the AI Chatbot Engine — a RAG-powered support/sales chatbot template. "
    "It combines OpenAI's chat and embedding models with a Postgres-backed knowledge "
    "base, so answers can be grounded in your own documents instead of the model's "
    "general knowledge alone.",

    "RAG stands for Retrieval-Augmented Generation. Before answering, the system embeds "
    "the incoming question, compares it against the embeddings of every stored document "
    "chunk, and injects the most similar chunks into the model's context. This lets the "
    "assistant answer questions about content it was never trained on.",

    "Conversation memory in this engine is persisted to Postgres per session_id, not just "
    "held in the browser. That means a conversation survives a page reload — the frontend "
    "just needs to keep reusing the same session_id (stored in localStorage by default).",

    "To add your own knowledge base content, insert rows into the `documents` table with "
    "the text you want retrievable — each row is embedded automatically the next time the "
    "app restarts with an empty table, or you can call the embedding step directly for a "
    "custom ingestion pipeline.",

    "This template ships with a real OpenAI integration out of the box. The LLM call is "
    "isolated behind a single function in app/chat.py, so swapping in a different provider "
    "(Claude, Mistral, etc.) means implementing one function rather than rewiring the app.",

    "Deployment: this is a standard FastAPI + React app, Docker-ready, deployable to Railway, "
    "Render, Fly.io, or any container host. Set DATABASE_URL to a Postgres connection string "
    "and OPENAI_API_KEY to enable chat — both are read from environment variables, never "
    "hardcoded.",
]


async def ensure_seeded(db: Session) -> None:
    if db.query(Document).first() is not None:
        return

    for content in SEED_DOCS:
        embedding = await embed_text(content)
        if embedding is None:
            logger.warning("Skipping knowledge-base seeding — OPENAI_API_KEY not set")
            return
        db.add(Document(content=content, embedding=embedding))
    db.commit()
    logger.info(f"Seeded {len(SEED_DOCS)} knowledge-base documents")
