"""Bounded, idempotent cleanup for expendable shopper data."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from qdrant_client import models

from shop.semantic_cache import COLLECTION
from shop.store import connect
from shop.vector_store import client

logger = logging.getLogger("shop.retention")
DEFAULT_CONVERSATION_DAYS = 30
DEFAULT_CACHE_DAYS = 7
DEFAULT_BATCH_SIZE = 100


def expire_conversations(*, now: datetime | None = None, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Tombstone old conversations after all pending work has become terminal."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    observed = now or datetime.now(timezone.utc)
    cutoff = observed - timedelta(days=int(os.environ.get("CONVERSATION_RETENTION_DAYS", DEFAULT_CONVERSATION_DAYS)))
    with connect() as db:
        rows = db.execute("""
            SELECT c.id FROM conversations c
            WHERE c.created_at < %s AND c.expired_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM questions q
                WHERE q.conversation_id = c.id AND q.status IN ('waiting', 'processing')
              )
            ORDER BY c.created_at LIMIT %s FOR UPDATE SKIP LOCKED
        """, (cutoff, batch_size)).fetchall()
        for row in rows:
            conversation_id = row["id"]
            db.execute("DELETE FROM work WHERE question_id IN (SELECT id FROM questions WHERE conversation_id = %s)", (conversation_id,))
            db.execute("DELETE FROM attempts WHERE question_id IN (SELECT id FROM questions WHERE conversation_id = %s)", (conversation_id,))
            db.execute("DELETE FROM questions WHERE conversation_id = %s", (conversation_id,))
            db.execute("UPDATE conversations SET expired_at = %s WHERE id = %s", (observed, conversation_id))
        return len(rows)


def expire_cache(*, now: datetime | None = None, qdrant: Any | None = None) -> int:
    """Delete cache vectors older than the configured TTL; safe to repeat."""
    observed = now or datetime.now(timezone.utc)
    cutoff = observed - timedelta(days=int(os.environ.get("CACHE_TTL_DAYS", DEFAULT_CACHE_DAYS)))
    qdrant = qdrant or client()
    try:
        if COLLECTION not in {item.name for item in qdrant.get_collections().collections}:
            return 0
        points, _ = qdrant.scroll(COLLECTION, limit=10_000, with_payload=True, with_vectors=False)
        expired = []
        for point in points:
            value = (point.payload or {}).get("created_at")
            try:
                created = datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if created < cutoff:
                expired.append(point.id)
        if expired:
            qdrant.delete(COLLECTION, points_selector=models.PointIdsList(points=expired))
        return len(expired)
    except Exception:
        logger.exception("cache_retention_failed")
        return 0


def run_once() -> dict[str, int]:
    """Run independent retention operations and report each result."""
    conversations = expire_conversations()
    cache = expire_cache()
    result = {"conversations": conversations, "cache": cache}
    logger.info("retention_complete conversations=%s cache=%s", conversations, cache)
    return result
