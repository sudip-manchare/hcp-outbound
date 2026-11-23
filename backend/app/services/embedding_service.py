"""Deterministic 384-dim text embeddings for Atlas Vector Search.

Uses hashed character trigrams (feature hashing) so scoring needs no model
download. The dimension matches all-MiniLM-L6-v2, so a sentence-transformer
can replace ``embed_text`` without changing the Atlas vector index.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from app.models.documents import EMBEDDING_DIM


def embed_text(text: str | None) -> list[float] | None:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    if not tokens:
        return None
    vector = np.zeros(EMBEDDING_DIM, dtype=float)
    for token in tokens:
        padded = f"#{token}#"
        for index in range(max(1, len(padded) - 2)):
            digest = hashlib.blake2b(padded[index:index + 3].encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
            vector[bucket] += 1.0 if digest[4] & 1 else -1.0
    norm = np.linalg.norm(vector)
    return (vector / norm).round(6).tolist() if norm else None

