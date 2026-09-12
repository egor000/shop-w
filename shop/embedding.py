"""Embedding seam. Production can replace the deterministic fallback with BGE."""
import hashlib
import math
import re
from typing import cast

MODEL_ID = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "73e8f7f"
PREPROCESSING_ID = "catalog-text-v1"
DIMENSION = 384


def preprocess(text: str) -> str:
    return "passage: " + " ".join(text.lower().split())


def embed(text: str) -> list[float]:
    if __import__("os").environ.get("EMBEDDING_BACKEND") == "bge":
        return BGEEmbedder().encode(text)
    # Repeatable CPU substitute for local integration tests; identity remains explicit.
    values = [0.0] * DIMENSION
    for token in re.findall(r"[a-z0-9]+", preprocess(text)):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % DIMENSION
        values[index] += 1.0 if digest[2] % 2 else -1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1
    return [value / norm for value in values]


class BGEEmbedder:
    """Optional real CPU embedder; loading is explicit to keep demos offline."""
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        self.model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, device="cpu")

    def encode(self, text: str) -> list[float]:
        return cast(list[float], self.model.encode(preprocess(text), normalize_embeddings=True).tolist())
