from uuid import uuid4

from tests.conftest import wait_for_question


def test_global_pending_admission_is_explicit_and_deduplicated(deployment):
    deployment.env["PENDING_QUESTION_LIMIT"] = "1"
    with deployment.api() as client:
        client.post("/api/session")
        first_conversation = client.post("/api/conversations").json()["id"]
        second_conversation = client.post("/api/conversations").json()["id"]
        payload = {"submission_id": str(uuid4()), "text": "What does the cup weigh?"}
        accepted = client.post(f"/api/conversations/{first_conversation}/questions", json=payload)
        assert accepted.status_code == 202
        duplicate = client.post(f"/api/conversations/{first_conversation}/questions", json=payload)
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == accepted.json()["id"]
        rejected = client.post(f"/api/conversations/{second_conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Find headphones",
        })
        assert rejected.status_code == 429
        assert rejected.headers["retry-after"] == "5"
        status = client.get("/api/operations/inference")
        assert status.status_code == 200
        assert status.json()["slot_limit"] == 2
        assert status.json()["pending_depth"] == 1


def test_two_workers_share_two_inference_slots(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversations = [client.post("/api/conversations").json()["id"] for _ in range(3)]
        questions = []
        for conversation in conversations:
            response = client.post(f"/api/conversations/{conversation}/questions", json={
                "submission_id": str(uuid4()), "text": "Describe the cup",
            })
            assert response.status_code == 202
            questions.append(response.json()["id"])
        with deployment.worker(DETERMINISTIC_DELAY_SECONDS="2", WORKER_LEASE_SECONDS="10"):
            with deployment.worker(DETERMINISTIC_DELAY_SECONDS="2", WORKER_LEASE_SECONDS="10"):
                statuses = []
                for conversation in conversations:
                    statuses.append(client.get(f"/api/conversations/{conversation}").json()["questions"][0]["status"])
                assert "waiting" in statuses or all(status == "processing" for status in statuses)
                for conversation in conversations:
                    wait_for_question(client, conversation, "completed")
