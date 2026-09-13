import json
import hashlib
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest


@contextmanager
def inference_server(responses, invalid=False):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            supplied = json.loads(body["messages"][-1]["content"])
            responses.append(supplied)
            payload = {"sentences": list(supplied["sentences"])}
            if invalid:
                payload["sentences"].append("unsupported lifetime warranty")
            encoded = json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def job(*arguments, check=True):
    return subprocess.run([sys.executable, "-m", "shop.catalog_jobs", *map(str, arguments)],
                          capture_output=True, text=True, check=check)


def test_facts_job_is_reproducible_with_complete_coherent_category_coverage(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    job("facts", "--output", first, "--count", 300, "--seed", 42)
    job("facts", "--output", second, "--count", 300, "--seed", 42)
    assert first.read_bytes() == second.read_bytes()
    products = [json.loads(line) for line in first.read_text().splitlines()]
    assert len({p["id"] for p in products}) == 300
    assert {p["department"] for p in products} == {"Electronics", "Home", "Office", "Sports", "Outdoors"}
    assert len({p["category"] for p in products}) == 10
    assert any(p["stock"] == 0 for p in products)
    assert any(p["rating_average"] is None and p["rating_count"] == 0 for p in products)
    assert len({p["name"] for p in products}) < 300
    for product in products:
        assert product["description"] == ""
        assert product["currency"] == "USD"
        assert product["url"] == "/products/" + product["id"]
        assert product["image_url"].startswith("/static/")
        assert product["available"] == (product["stock"] > 0)
        assert product["measurement_configuration"]
        if product["category"] == "Yoga mats":
            assert product["height_cm"] == product["attributes"]["thickness_mm"] / 10
        if product["category"] == "Headphones" and product["attributes"]["connection"] == "wired":
            assert product["attributes"]["battery_hours"] == 0


def test_offline_jobs_resume_approved_descriptions_and_freeze_verifiable_artifact(tmp_path):
    facts, progress, artifact = tmp_path / "facts.jsonl", tmp_path / "progress.sqlite", tmp_path / "frozen"
    job("facts", "--output", facts, "--count", 20)
    calls = []
    with inference_server(calls) as url:
        job("describe", "--facts", facts, "--progress", progress, "--url", url, "--model", "controlled", "--max-products", 7)
        incomplete = job("freeze", "--facts", facts, "--progress", progress, "--output", artifact, check=False)
        assert incomplete.returncode != 0
        assert not artifact.exists()
        job("describe", "--facts", facts, "--progress", progress, "--url", url, "--model", "controlled")
        assert len(calls) == 20
        job("describe", "--facts", facts, "--progress", progress, "--url", url, "--model", "controlled")
        assert len(calls) == 20
    job("freeze", "--facts", facts, "--progress", progress, "--output", artifact)
    result = job("validate", "--artifact", artifact)
    assert json.loads(result.stdout)["count"] == 20
    manifest = json.loads((artifact / "manifest.json").read_text())
    assert manifest["schema_version"] and manifest["generator_version"]
    assert manifest["seed"] == 42 and manifest["count"] == 20
    assert manifest["description_model"] == "controlled"
    assert len(manifest["sha256"]) == 64
    products = [json.loads(line) for line in (artifact / "products.jsonl").read_text().splitlines()]
    assert all(p["description"] and "fictional" in p["description"] for p in products)
    (artifact / "products.jsonl").write_text("corrupted\n")
    assert job("validate", "--artifact", artifact, check=False).returncode != 0


@pytest.mark.parametrize("field,value", [
    ("price_cents", -1), ("stock", -1), ("rating_count", 1), ("rating_average", 4.5),
    ("department", "Home"), ("currency", "EUR"), ("url", "https://external.example/product"),
    ("available", True), ("length_cm", 0), ("attributes", {"battery_hours": 900}),
])
def test_description_job_rejects_invalid_structured_facts_before_inference(tmp_path, field, value):
    facts = tmp_path / "facts.jsonl"
    job("facts", "--output", facts, "--count", 10)
    products = [json.loads(line) for line in facts.read_text().splitlines()]
    products[0][field] = value
    facts.write_text("\n".join(json.dumps(p) for p in products) + "\n")
    metadata_path = facts.with_suffix(".manifest.json")
    metadata = json.loads(metadata_path.read_text())
    metadata["sha256"] = hashlib.sha256(facts.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata))
    calls = []
    with inference_server(calls) as url:
        result = job("describe", "--facts", facts, "--progress", tmp_path / "progress.sqlite", "--url", url, check=False)
    assert result.returncode != 0
    assert not calls


def test_unsupported_model_claims_are_rejected_and_can_be_retried(tmp_path):
    facts, progress, artifact = tmp_path / "facts.jsonl", tmp_path / "progress.sqlite", tmp_path / "frozen"
    job("facts", "--output", facts, "--count", 10)
    with inference_server([], invalid=True) as url:
        rejected = job("describe", "--facts", facts, "--progress", progress, "--url", url, check=False)
    assert rejected.returncode != 0
    assert "unsupported" in rejected.stderr
    assert job("freeze", "--facts", facts, "--progress", progress, "--output", artifact, check=False).returncode != 0
    with inference_server([]) as url:
        job("describe", "--facts", facts, "--progress", progress, "--url", url)
    job("freeze", "--facts", facts, "--progress", progress, "--output", artifact)
    assert job("validate", "--artifact", artifact).returncode == 0


def test_generated_template_fixture_is_ingested_and_visible_through_public_application(tmp_path, deployment):
    facts, progress, artifact = tmp_path / "facts.jsonl", tmp_path / "progress.sqlite", tmp_path / "frozen"
    job("facts", "--output", facts, "--count", 30)
    calls = []
    with inference_server(calls) as url:
        job("describe", "--facts", facts, "--progress", progress, "--url", url, "--mode", "templates")
    assert len(calls) == 10
    job("freeze", "--facts", facts, "--progress", progress, "--output", artifact, "--gzip")
    release = "generated-" + uuid4().hex
    env = {**deployment.env, "CATALOG_ARTIFACT": str(artifact), "CATALOG_RELEASE": release,
           "QDRANT_URL": os.environ.get("TEST_QDRANT_URL", "http://127.0.0.1:6333")}
    subprocess.run([sys.executable, "-m", "shop.ingest"], env=env, check=True)
    deployment.env.update({"QDRANT_URL": env["QDRANT_URL"]})
    with deployment.api() as api:
        readiness = api.get("/api/catalog/readiness").json()
        assert readiness["product_count"] == 30
        assert readiness["release"] == release
        result = api.get("/api/products/search", params={"q": "headphones", "category": "Headphones"})
        assert result.status_code == 200
        products = result.json()["products"]
        assert len(products) == 3
        unrated = next(product for product in products if product["id"] == "review-42-000001")
        assert unrated["rating_average"] is None and unrated["stock"] == 0
        detail = api.get(unrated["url"])
        assert detail.status_code == 200
        assert "Unrated" in detail.text
        assert "assembled product" in detail.text
        assert "Battery life" in detail.text
        assert api.get("/static/product-placeholder.svg").status_code == 200
