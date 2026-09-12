import os
from typing import Any

from qdrant_client import QdrantClient, models

from shop.catalog import CatalogProduct
from shop.embedding import DIMENSION, MODEL_ID, PREPROCESSING_ID, embed

COLLECTION = "catalog_products"


def client() -> QdrantClient:
    return QdrantClient(url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"), timeout=5)


def ensure_collection(qdrant: QdrantClient) -> None:
    names = {item.name for item in qdrant.get_collections().collections}
    config: Any = qdrant.get_collection(COLLECTION).config if COLLECTION in names else None
    vectors: Any = config.params.vectors if config is not None else None
    vector_size: Any = getattr(vectors, "size", None)
    if isinstance(vectors, dict):
        vector_size = getattr(vectors.get(""), "size", None)
    if COLLECTION in names and vector_size != DIMENSION:
        qdrant.delete_collection(COLLECTION)
        names.remove(COLLECTION)
    if COLLECTION not in names:
        qdrant.create_collection(COLLECTION, vectors_config=models.VectorParams(size=DIMENSION, distance=models.Distance.COSINE))


def upsert(qdrant: QdrantClient, products: list[CatalogProduct], release: str, batch_size: int = 50) -> None:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    ensure_collection(qdrant)
    for start in range(0, len(products), batch_size):
        batch = products[start:start + batch_size]
        qdrant.upsert(COLLECTION, points=[models.PointStruct(id=start + index + 1, vector=embed(product.text()), payload={"product_id": product.id, "release": release, "embedding_model": MODEL_ID, "preprocessing": PREPROCESSING_ID}) for index, product in enumerate(batch)])


def search(query: str, release: str, limit: int = 10, score_threshold: float = .4) -> list[str]:
    if not query.strip():
        return []
    qdrant = client()
    if COLLECTION not in {item.name for item in qdrant.get_collections().collections}:
        raise RuntimeError("catalog_not_ready")
    result = qdrant.query_points(collection_name=COLLECTION, query=embed(query), query_filter=models.Filter(must=[models.FieldCondition(key="release", match=models.MatchValue(value=release))]), score_threshold=score_threshold, limit=limit, with_payload=True)
    return [str(point.payload["product_id"]) for point in result.points if point.payload and "product_id" in point.payload]
