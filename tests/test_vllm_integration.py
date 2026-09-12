import os
import time
from uuid import uuid4

import httpx
import pytest
from tests.test_catalog import catalog_deployment


def _vllm_ready(url: str) -> bool:
    try:
        return httpx.get(url.rstrip("/") + "/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def test_real_vllm_end_to_end(catalog_deployment):
    if os.environ.get("RUN_VLLM_INTEGRATION") != "1":
        pytest.skip("set RUN_VLLM_INTEGRATION=1 after starting docker compose --profile vllm")
    deployment, _, _ = catalog_deployment
    vllm_url = os.environ.get("VLLM_URL", "http://127.0.0.1:8000")
    if not _vllm_ready(vllm_url):
        pytest.skip("vLLM health endpoint is unavailable")
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        submitted = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Which headphones have noise reduction?",
        })
        assert submitted.status_code == 202
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=vllm_url, VLLM_MODEL="Qwen/Qwen3-1.7B"):
            for _ in range(180):
                question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                if question["status"] in {"completed", "failed", "expired"}:
                    break
                time.sleep(1)
            else:
                pytest.fail("real vLLM answer did not complete")
        assert question["status"] == "completed"
        assert question["answer"]["products"]
        assert question["answer"]["products"][0]["url"] == "/products/aurora-headphones"
