"""Best-effort semantic reuse for standalone public product answers."""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import models

from shop.embedding import CACHE_PREPROCESSING_ID, DIMENSION, MODEL_ID, MODEL_REVISION, embed_cache_question
from shop.models import ProductAnswer
from shop.store import connect, products_by_ids, product_search_release
from shop.vector_store import client

COLLECTION = "semantic_cache_answers"
CHAT_MODEL_ID = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-1.7B")
PROMPT_ID = "grounded-product-answer-v1"
TOOL_SCHEMA_ID = "product-read-v1"
DEFAULT_TTL_DAYS = 7
DEFAULT_MAX_ENTRIES = 10_000
logger = logging.getLogger("shop.semantic_cache")


def _canonical(question: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", question.lower()))


def _constraints(question: str) -> str:
    """Return a conservative constraint signature for compatibility checks."""
    text = _canonical(question)
    numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", text)
    categories = sorted(category for category in (
        "headphones", "portable speakers", "electric kettles", "table lamps",
        "keyboards", "desk organizers", "yoga mats", "dumbbells", "backpacks",
        "camping lanterns",
    ) if category in text)
    return "|".join([*categories, *numbers])


def eligible(question: str, *, standalone: bool) -> bool:
    """Only cache public first-turn, single-product factual questions."""
    if not standalone:
        return False
    lowered = question.lower()
    excluded = ("compare", "versus", " vs ", "my order", "i bought", "i own",
                "earlier", "previous", "above", "that product", "recommend me")
    return not any(marker in lowered for marker in excluded)


def _ensure_collection(qdrant: Any) -> None:
    names = {item.name for item in qdrant.get_collections().collections}
    if COLLECTION in names:
        config = qdrant.get_collection(COLLECTION).config
        vectors = config.params.vectors
        size = getattr(vectors, "size", None)
        if size != DIMENSION:
            qdrant.delete_collection(COLLECTION)
            names.remove(COLLECTION)
    if COLLECTION not in names:
        qdrant.create_collection(COLLECTION, vectors_config=models.VectorParams(
            size=DIMENSION, distance=models.Distance.COSINE))


def _compatible(payload: dict[str, Any], release: str) -> bool:
    try:
        created_at = datetime.fromisoformat(str(payload.get("created_at"))).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return (payload.get("catalog_release") == release
            and payload.get("locale") == "en-US"
            and payload.get("embedding_model") == MODEL_ID
            and payload.get("embedding_revision") == MODEL_REVISION
            and payload.get("preprocessing") == CACHE_PREPROCESSING_ID
            and payload.get("chat_model") == CHAT_MODEL_ID
            and payload.get("prompt") == PROMPT_ID
            and payload.get("tool_schema") == TOOL_SCHEMA_ID
            and created_at >= datetime.now(timezone.utc) - timedelta(days=float(os.environ.get("CACHE_TTL_DAYS", DEFAULT_TTL_DAYS))))


def lookup(question: str, *, standalone: bool) -> ProductAnswer | None:
    release = product_search_release()
    if not release or not eligible(question, standalone=standalone):
        logger.info("cache_decision=reject reason=eligibility")
        return None
    qdrant = client()
    try:
        if COLLECTION not in {item.name for item in qdrant.get_collections().collections}:
            logger.info("cache_decision=miss reason=collection_absent")
            return None
        result = qdrant.query_points(
            collection_name=COLLECTION, query=embed_cache_question(question), limit=3,
            score_threshold=float(os.environ.get("CACHE_SCORE_THRESHOLD", ".60")), with_payload=True)
    except Exception:
        logger.info("cache_decision=miss reason=lookup_unavailable")
        return None
    signature = _constraints(question)
    for point in result.points:
        payload = point.payload or {}
        if not _compatible(payload, release) or payload.get("constraints") != signature:
            continue
        try:
            answer = ProductAnswer.model_validate(payload["answer"])
            ids = [link.url.rsplit("/", 1)[-1] for link in answer.products]
            products = products_by_ids(ids)
            if len(products) != len(ids) or any(product.stock < 0 for product in products):
                continue
            logger.info("cache_decision=hit score=%s", point.score)
            return answer
        except Exception:
            continue
    logger.info("cache_decision=miss reason=no_compatible_entry")
    return None


def put(question: str, answer: ProductAnswer, *, standalone: bool) -> None:
    release = product_search_release()
    if not release or not eligible(question, standalone=standalone) or not answer.products:
        return
    try:
        ids = [link.url.rsplit("/", 1)[-1] for link in answer.products]
        products = products_by_ids(ids)
        if len(products) != len(ids):
            return
        qdrant = client()
        _ensure_collection(qdrant)
        now = datetime.now(timezone.utc).isoformat()
        key = hashlib.sha256(f"{release}|{_canonical(question)}|{_constraints(question)}".encode()).hexdigest()
        payload = {"catalog_release": release, "locale": "en-US", "embedding_model": MODEL_ID,
                   "embedding_revision": MODEL_REVISION, "preprocessing": CACHE_PREPROCESSING_ID,
                   "chat_model": CHAT_MODEL_ID, "prompt": PROMPT_ID, "tool_schema": TOOL_SCHEMA_ID,
                   "constraints": _constraints(question), "created_at": now,
                   "answer": answer.model_dump()}
        qdrant.upsert(COLLECTION, points=[models.PointStruct(
            id=str(uuid5(NAMESPACE_URL, key)), vector=embed_cache_question(question), payload=payload)])
        cap = int(os.environ.get("CACHE_MAX_ENTRIES", DEFAULT_MAX_ENTRIES))
        if cap <= 0:
            raise ValueError("CACHE_MAX_ENTRIES must be positive")
        count = qdrant.count(COLLECTION).count
        if count > cap:
            points, _ = qdrant.scroll(COLLECTION, limit=count, with_payload=True, with_vectors=False)
            expired = sorted(points, key=lambda point: str((point.payload or {}).get("created_at", "")))[:count - cap]
            if expired:
                qdrant.delete(COLLECTION, points_selector=models.PointIdsList(
                    points=[point.id for point in expired]))
        logger.info("cache_decision=stored")
    except Exception:
        # Cache is an optimization; completed answers must survive its failure.
        logger.info("cache_decision=store_failed")
