"""OpenAI embeddings + cosine similarity for the RAG retrieval step."""
import os
from typing import List, Optional

from openai import AsyncOpenAI

EMBEDDING_MODEL = "text-embedding-3-small"


def _get_client() -> Optional[AsyncOpenAI]:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return AsyncOpenAI()


async def embed_text(text: str) -> Optional[List[float]]:
    client = _get_client()
    if client is None:
        return None
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
