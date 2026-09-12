"""Public lifecycle checks for the expendable semantic answer cache."""
import time
from uuid import uuid4

from qdrant_client import QdrantClient

from shop.semantic_cache import COLLECTION
from tests.test_catalog import catalog_deployment


def _complete(client, conversation):
    for _ in range(100):
        question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
        if question["status"] == "completed":
            return question
        time.sleep(.1)
    raise AssertionError("question did not complete")


def test_eligible_paraphrase_reuses_saved_answer_and_history_is_bypassed(catalog_deployment):
    deployment, qdrant, _ = catalog_deployment
    try:
        qdrant.delete_collection(COLLECTION)
    except Exception:
        pass
    with deployment.api() as client:
        client.post("/api/session")
        first_conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{first_conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Which headphones have noise reduction?"})
        with deployment.worker():
            first = _complete(client, first_conversation)

        second_conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{second_conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Which headphones provide noise reduction?"})
        with deployment.controlled_worker(TEST_INFERENCE_RESULT="cache miss"):
            second = _complete(client, second_conversation)
        assert second["answer"] == first["answer"]

        followup_conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{followup_conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Which headphones have noise reduction?"})
        with deployment.worker():
            _complete(client, followup_conversation)
        followup = client.post(f"/api/conversations/{followup_conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "What is its weight?"})
        assert followup.status_code == 202
        with deployment.controlled_worker(TEST_INFERENCE_RESULT="cache miss"):
            followup_result = _complete(client, followup_conversation)
        # History-dependent questions bypass the first-turn cache.
        assert followup_result["answer"] != first["answer"]
