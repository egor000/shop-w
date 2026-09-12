"""Freeze the fixture into PostgreSQL and Qdrant, then publish readiness."""
import logging
import os
from uuid import uuid4

from psycopg.types.json import Jsonb

from shop.catalog import CATALOG
from shop.embedding import MODEL_ID, PREPROCESSING_ID
from shop.store import connect
from shop.vector_store import COLLECTION, upsert, client
from qdrant_client import models

logger = logging.getLogger("shop.ingest")


def main() -> None:
    release = os.environ.get("CATALOG_RELEASE", "demo-2026-09-12")
    with connect() as db:
        db.execute("INSERT INTO catalog_releases (id, product_count, embedding_model, preprocessing, status) VALUES (%s, %s, %s, %s, 'loading') ON CONFLICT (id) DO UPDATE SET status = 'loading', product_count = EXCLUDED.product_count, embedding_model = EXCLUDED.embedding_model, preprocessing = EXCLUDED.preprocessing, ready_at = NULL", (release, len(CATALOG), MODEL_ID, PREPROCESSING_ID))
        completed = {row["batch_start"] for row in db.execute("SELECT batch_start FROM catalog_progress WHERE release_id = %s", (release,)).fetchall()}
        for start in range(0, len(CATALOG), 50):
            batch = CATALOG[start:start + 50]
            if start in completed:
                continue
            for product in batch:
                db.execute("INSERT INTO products (id, facts) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET facts = EXCLUDED.facts", (product.id, Jsonb(product.facts())))
            db.execute("INSERT INTO catalog_progress VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (release, start, start + len(batch)))
    qdrant = client()
    upsert(qdrant, list(CATALOG), release)
    release_filter = models.Filter(must=[models.FieldCondition(key="release", match=models.MatchValue(value=release))])
    vector_count = qdrant.count(COLLECTION, count_filter=release_filter).count
    points, _ = qdrant.scroll(COLLECTION, scroll_filter=release_filter, limit=len(CATALOG), with_payload=True, with_vectors=False)
    expected_ids = {product.id for product in CATALOG}
    vector_ids = {str(point.payload.get("product_id")) for point in points if point.payload}
    metadata_ok = all(point.payload and point.payload.get("embedding_model") == MODEL_ID and point.payload.get("preprocessing") == PREPROCESSING_ID for point in points)
    with connect() as db:
        fact_row = db.execute("SELECT count(*) AS count FROM products WHERE id = ANY(%s)", ([product.id for product in CATALOG],)).fetchone()
        assert fact_row is not None
        fact_count = fact_row["count"]
    if vector_count != len(CATALOG) or vector_ids != expected_ids or not metadata_ok or fact_count != len(CATALOG):
        raise RuntimeError("catalog_vectors_incomplete")
    with connect() as db:
        db.execute("UPDATE catalog_releases SET status = 'ready', ready_at = clock_timestamp() WHERE id = %s", (release,))
    logger.info("catalog_release=%s status=ready products=%s", release, len(CATALOG))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
