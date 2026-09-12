"""Retention keeps active work safe and makes expired history explicit."""
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import psycopg

from shop.retention import expire_cache, expire_conversations
from shop.semantic_cache import COLLECTION
from tests.test_catalog import catalog_deployment


def test_old_conversation_is_tombstoned_but_pending_work_is_preserved(deployment):
    os.environ["DATABASE_URL"] = deployment.env["DATABASE_URL"]
    os.environ["PGOPTIONS"] = deployment.env["PGOPTIONS"]
    with deployment.api() as client:
        client.post("/api/session")
        old = client.post("/api/conversations").json()["id"]
        pending = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{old}/questions", json={"submission_id": str(uuid4()), "text": "old"})
        client.post(f"/api/conversations/{pending}/questions", json={"submission_id": str(uuid4()), "text": "pending"})
        with psycopg.connect(deployment.env["DATABASE_URL"], options=deployment.env["PGOPTIONS"]) as db:
            db.execute("UPDATE conversations SET created_at = clock_timestamp() - interval '31 days' WHERE id = %s", (old,))
            db.execute("UPDATE conversations SET created_at = clock_timestamp() - interval '31 days' WHERE id = %s", (pending,))
            db.execute("UPDATE questions SET status = 'completed', answer = '{\"text\":\"saved\",\"products\":[]}' WHERE conversation_id = %s", (old,))
        assert expire_conversations() == 1
        assert client.get(f"/api/conversations/{old}").status_code == 410
        assert client.get(f"/api/conversations/{pending}").status_code == 200


def test_cache_retention_removes_old_entries_and_is_idempotent(catalog_deployment):
    deployment, qdrant, _ = catalog_deployment
    try:
        qdrant.delete_collection(COLLECTION)
    except Exception:
        pass
    from qdrant_client import models
    qdrant.create_collection(COLLECTION, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    qdrant.upsert(COLLECTION, points=[models.PointStruct(id=str(uuid4()), vector=[0.0] * 384, payload={"created_at": old})])
    assert expire_cache(qdrant=qdrant) == 1
    assert expire_cache(qdrant=qdrant) == 0
