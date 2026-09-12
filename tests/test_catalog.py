import os
import subprocess
import sys
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from shop.catalog import CATALOG
from shop.embedding import MODEL_ID, PREPROCESSING_ID
from shop.vector_store import COLLECTION


@pytest.fixture
def catalog_deployment(deployment):
    qdrant_url = os.environ.get("TEST_QDRANT_URL", "http://127.0.0.1:6333")
    client = QdrantClient(url=qdrant_url, timeout=5)
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    env = {**deployment.env, "QDRANT_URL": qdrant_url, "CATALOG_RELEASE": "test-" + uuid4().hex}
    subprocess.run([sys.executable, "-m", "shop.ingest"], env=env, check=True)
    return deployment, client, env["CATALOG_RELEASE"]


def test_ingestion_publishes_frozen_hierarchy_to_postgres_and_qdrant(catalog_deployment):
    deployment, qdrant, release = catalog_deployment
    assert qdrant.count(COLLECTION).count == len(CATALOG)
    with deployment.api_process() as (api, _):
        ready = api.get("/api/catalog/readiness")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready", "release": release, "product_count": 10,
                                "embedding_model": MODEL_ID, "preprocessing": PREPROCESSING_ID}
        operations = api.get("/api/catalog/operations")
        assert operations.status_code == 200
        assert operations.json()["status"] == "ready"
        assert operations.json()["completed_items"] == 10
        result = api.get("/api/products/search", params={"q": "wireless headphones", "category": "Headphones"})
        assert result.status_code == 200
        products = result.json()["products"]
        assert len(products) == 1
        assert products[0]["id"] == "aurora-headphones"
        detail = api.get(products[0]["url"])
        assert detail.status_code == 200
        assert "Aurora Headphones" in detail.text
        assert "Northstar" in detail.text


def test_department_filter_includes_its_leaf_categories(catalog_deployment):
    deployment, _, _ = catalog_deployment
    with deployment.api_process() as (api, _):
        result = api.get("/api/products/search", params={"q": "home", "department": "Home"})
        assert result.status_code == 200
        assert {product["category"] for product in result.json()["products"]} == {"Electric kettles", "Table lamps"}


def test_structured_constraints_filter_authoritative_product_facts(catalog_deployment):
    deployment, _, _ = catalog_deployment
    with deployment.api_process() as (api, _):
        result = api.get("/api/products/search", params={
            "q": "wireless headphones", "category": "Headphones", "max_price_cents": 9000, "min_rating": 4.0,
            "max_weight_kg": .5, "in_stock": "true", "attribute": "connection=bluetooth",
        })
        assert result.status_code == 200
        products = result.json()["products"]
        assert [product["id"] for product in products] == ["aurora-headphones"]
        assert products[0]["measurement_basis"] == "product, excluding packaging"
        rejected = api.get("/api/products/search", params={"q": "wireless headphones", "max_price_cents": 1000})
        assert rejected.status_code == 200
        assert rejected.json()["products"] == []


def test_unready_catalog_is_explicit_and_search_does_not_fabricate(catalog_deployment):
    deployment, qdrant, _ = catalog_deployment
    qdrant.delete_collection(COLLECTION)
    with deployment.api_process() as (api, _):
        assert api.get("/api/products/search", params={"q": "anything"}).status_code == 503
        assert api.get("/api/catalog/readiness").status_code == 200


def test_ready_catalog_no_match_is_a_limitation_not_a_legacy_product(catalog_deployment):
    deployment, _, _ = catalog_deployment
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Find a product made of moon cheese",
        })
        with deployment.worker():
            for _ in range(100):
                question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                if question["status"] == "completed":
                    break
                import time
                time.sleep(.1)
            else:
                pytest.fail("no-match answer did not complete")
        assert question["answer"]["products"] == []
        assert "could not find" in question["answer"]["text"].lower()


def test_saved_answer_uses_qdrant_match_when_catalog_is_ready(catalog_deployment):
    deployment, _, _ = catalog_deployment
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Which headphones have noise reduction?",
        })
        assert response.status_code == 202
        with deployment.worker():
            for _ in range(100):
                question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                if question["status"] == "completed":
                    break
                import time
                time.sleep(.1)
            else:
                pytest.fail("catalog answer did not complete")
        assert question["answer"]["products"][0]["url"] == "/products/aurora-headphones"
        assert "Aurora Headphones" in question["answer"]["text"]


def test_real_bge_retrieval_smoke_when_weights_are_installed(catalog_deployment, monkeypatch):
    if not os.environ.get("RUN_REAL_EMBEDDING_SMOKE"):
        pytest.skip("Set RUN_REAL_EMBEDDING_SMOKE=1 after installing requirements-real-embeddings.txt")
    monkeypatch.setenv("EMBEDDING_BACKEND", "bge")
    deployment, qdrant, release = catalog_deployment
    qdrant.delete_collection(COLLECTION)
    env = {**deployment.env, "QDRANT_URL": os.environ.get("TEST_QDRANT_URL", "http://127.0.0.1:6333"), "CATALOG_RELEASE": release, "EMBEDDING_BACKEND": "bge"}
    subprocess.run([sys.executable, "-m", "shop.ingest"], env=env, check=True)
    from shop.embedding import BGEEmbedder
    model = BGEEmbedder()
    assert len(model.encode("wireless headphones")) == 384
    assert qdrant.count(COLLECTION, count_filter={"must": [{"key": "release", "match": {"value": release}}]}).count == 10
    from shop.vector_store import search
    assert search("wireless headphones", release, limit=1)[0] == "aurora-headphones"
