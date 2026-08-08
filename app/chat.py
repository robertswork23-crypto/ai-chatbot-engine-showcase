"""Chat orchestration: retrieve relevant knowledge-base chunks, call the LLM,
persist both turns as real conversation memory (not just what the browser
resends).
"""
import logging
import os
from datetime import datetime
from typing import List

import openai
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from .db import Document, Message
from .embeddings import cosine_similarity, embed_text

logger = logging.getLogger(__name__)

# LLM provider routing. Only "openai" is implemented and tested in this
# template — the marketing framing of "multi-LLM routing" means the call is
# isolated behind this one function, so adding Claude/Mistral is a matter of
# implementing another branch here, not rewiring the app. Claiming those
# providers work today without keys or tests to back it up would be false,
# so they raise clearly instead of silently no-op-ing.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
MODEL = "gpt-5.6-luna"

SYSTEM_PROMPT = """You are the AI Chatbot Engine demo assistant — a RAG-powered support
chatbot template. Answer using the CONTEXT block below when it's relevant to the
question; if the context doesn't cover it, answer from general knowledge and say so.
Be concise and helpful. Be upfront that this is a demo instance if asked."""

TOP_K = 3


def _get_client():
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return AsyncOpenAI()


async def _retrieve_context(db: Session, message: str) -> str:
    query_embedding = await embed_text(message)
    if query_embedding is None:
        return ""

    docs = db.query(Document).all()
    if not docs:
        return ""

    scored = sorted(
        ((cosine_similarity(query_embedding, d.embedding), d.content) for d in docs),
        key=lambda pair: pair[0],
        reverse=True,
    )
    top = [content for _, content in scored[:TOP_K]]
    return "\n\n".join(f"- {c}" for c in top)


async def get_chat_reply(db: Session, session_id: str, message: str) -> str:
    if LLM_PROVIDER != "openai":
        raise NotImplementedError(
            f"LLM_PROVIDER={LLM_PROVIDER!r} is not implemented in this template — only 'openai' is wired up."
        )

    client = _get_client()
    if client is None:
        logger.warning("Chat requested but OPENAI_API_KEY is not set")
        return "Chat isn't configured yet on this deployment — add an OPENAI_API_KEY to enable it."

    history: List[Message] = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(20)
        .all()
    )
    conversation = [{"role": m.role, "content": m.content} for m in history]
    conversation.append({"role": "user", "content": message})

    context = await _retrieve_context(db, message)
    instructions = SYSTEM_PROMPT
    if context:
        instructions += f"\n\nCONTEXT:\n{context}"

    try:
        response = await client.responses.create(
            model=MODEL,
            instructions=instructions,
            input=conversation,
            max_output_tokens=1024,
        )
    except openai.AuthenticationError:
        logger.error("Chat auth failed — check OPENAI_API_KEY")
        return "Chat is misconfigured right now. Please try again later."
    except openai.RateLimitError:
        return "Getting a lot of questions right now — try again in a moment."
    except openai.APIConnectionError:
        return "Couldn't reach the chat service. Please try again in a moment."
    except openai.APIStatusError as e:
        logger.error(f"Chat API error: {e.status_code} {e.message}")
        return "Something went wrong answering that. Please try again."

    reply = (response.output_text or "").strip() or "I don't have a good answer for that one — try rephrasing?"

    db.add(Message(session_id=session_id, role="user", content=message, created_at=datetime.utcnow()))
    db.add(Message(session_id=session_id, role="assistant", content=reply, created_at=datetime.utcnow()))
    db.commit()

    return reply
