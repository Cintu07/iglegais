"""shared sentence embeddings.

one model, loaded once, used by every backend. 384-dim, local, normalized
so cosine similarity is just a dot product.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L6-v2")


def embed(text: str) -> list[float]:
    return _model.encode(text, normalize_embeddings=True).tolist()
