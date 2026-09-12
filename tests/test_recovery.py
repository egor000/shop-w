from uuid import uuid4
import time
import pytest
import httpx
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import kill_process_tree, process_tree, wait_for_question


def test_another_worker_recovers_a_question_after_its_owner_is_killed(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        payload = {"submission_id": str(uuid4()), "text": "What does the Trail Cup weigh?"}
        accepted = client.post(f"/api/conversations/{conversation}/questions", json=payload).json()
        with deployment.worker(DETERMINISTIC_DELAY_SECONDS="30", WORKER_LEASE_SECONDS="1.5") as worker:
            wait_for_question(client, conversation, "processing")
            kill_process_tree(worker)
        with deployment.worker(WORKER_LEASE_SECONDS="1.5"):
            completed = wait_for_question(client, conversation, "completed")
        assert completed["id"] == accepted["id"]
        assert completed["deadline"] == accepted["deadline"]
        assert completed["attempt_count"] == 2
        assert completed["recovery_count"] == 1
        assert "0.25 kg" in completed["answer"]["text"]
        assert client.post(f"/api/conversations/{conversation}/questions", json=payload).json() == completed


def test_transient_retry_budget_survives_worker_restart(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        accepted = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "What is the cup price?",
        }).json()
        with deployment.controlled_worker(TEST_INFERENCE_ERROR="transient"):
            for _ in range(100):
                question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                if question["attempt_count"] == 1 and question["status"] != "processing":
                    break
                time.sleep(.05)
            else:
                pytest.fail("First transient failure did not become observable")
            assert question["status"] == "waiting"
            waiting = client.get(f"/api/operations/questions/{question['id']}").json()
            assert waiting["next_attempt_at"] > waiting["attempts"][0]["finished_at"]
            assert waiting["next_attempt_at"] < waiting["deadline"]
        with deployment.controlled_worker(TEST_INFERENCE_ERROR="transient"):
            failed = wait_for_question(client, conversation, "failed")
        assert failed["attempt_count"] == 3
        assert failed["deadline"] == accepted["deadline"]
        assert failed["last_error"] == "attempts_exhausted"
        assert failed["answer"] is None
        operations = client.get(f"/api/operations/questions/{failed['id']}")
        assert operations.status_code == 200
        metadata = operations.json()
        assert metadata["attempt_count"] == 3
        assert [attempt["number"] for attempt in metadata["attempts"]] == [1, 2, 3]
        assert all(attempt["finished_at"] for attempt in metadata["attempts"])
        assert "What is the cup price?" not in operations.text
        assert "raw provider text" not in operations.text


def test_permanent_inference_failure_is_not_retried(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Question with an invalid provider response",
        })
        with deployment.controlled_worker(TEST_INFERENCE_ERROR="permanent"):
            failed = wait_for_question(client, conversation, "failed")
        assert failed["attempt_count"] == 1
        assert failed["last_error"] == "permanent_inference"
        assert failed["answer"] is None


def test_healthy_worker_renews_ownership_while_inference_takes_longer_than_lease(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Tell me about the cup",
        })
        with deployment.worker(DETERMINISTIC_DELAY_SECONDS="4", WORKER_LEASE_SECONDS="1.5"):
            wait_for_question(client, conversation, "processing")
            with deployment.worker(WORKER_LEASE_SECONDS="1.5"):
                completed = wait_for_question(client, conversation, "completed")
        assert completed["attempt_count"] == 1
        assert completed["recovery_count"] == 0


def test_expired_owner_cannot_publish_even_before_a_replacement_claims_work(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Describe the cup",
        })
        with deployment.worker(DETERMINISTIC_DELAY_SECONDS="2", WORKER_LEASE_SECONDS="1") as worker:
            wait_for_question(client, conversation, "processing")
            owners = process_tree(worker)
            for owner in owners:
                owner.suspend()
            try:
                time.sleep(2.5)  # Let the persisted lease expire while the whole owner is paused.
            finally:
                for owner in reversed(owners):
                    owner.resume()
            completed = wait_for_question(client, conversation, "completed")
        assert completed["attempt_count"] == 2
        assert completed["recovery_count"] == 1


def test_api_death_after_commit_before_acknowledgement_is_safe_to_retry(deployment):
    with deployment.api_process("tests.delayed_api:app") as (first, process), deployment.api() as second:
        first.post("/api/session")
        second.cookies.update(dict(first.cookies))
        conversation = first.post("/api/conversations").json()["id"]
        path = f"/api/conversations/{conversation}/questions"
        payload = {"submission_id": str(uuid4()), "text": "Question with an interrupted acknowledgement"}
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(first.post, path, json=payload, timeout=15)
            accepted = wait_for_question(second, conversation, "waiting")
            assert not pending.done()
            kill_process_tree(process)
            with pytest.raises(httpx.TransportError):
                pending.result(timeout=5)
        assert second.post(path, json=payload).json() == accepted
        with deployment.worker():
            completed = wait_for_question(second, conversation, "completed")
        assert completed["id"] == accepted["id"]
        assert second.get(f"/api/conversations/{conversation}").json()["questions"] == [completed]


def test_obsolete_worker_cannot_replace_a_newer_saved_answer(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "A question crossing two attempts",
        })
        with deployment.controlled_worker(TEST_INFERENCE_DELAY="3", TEST_INFERENCE_RESULT="Obsolete answer", WORKER_LEASE_SECONDS="1") as first:
            wait_for_question(client, conversation, "processing")
            owners = process_tree(first)
            for owner in owners:
                owner.suspend()
            try:
                with deployment.controlled_worker(TEST_INFERENCE_RESULT="Authoritative answer", WORKER_LEASE_SECONDS="1"):
                    saved = wait_for_question(client, conversation, "completed")
                assert saved["answer"]["text"] == "Authoritative answer"
            finally:
                for owner in reversed(owners):
                    owner.resume()
            time.sleep(3.5)  # Allow the obsolete delayed inference to return.
            assert client.get(f"/api/conversations/{conversation}").json()["questions"] == [saved]
        operations = client.get(f"/api/operations/questions/{saved['id']}").json()
        assert [attempt["outcome"] for attempt in operations["attempts"]] == ["abandoned", "completed"]


def test_repeated_worker_death_cannot_reset_the_attempt_budget(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        accepted = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "A question whose workers keep dying",
        }).json()
        for number in (1, 2, 3):
            with deployment.worker(DETERMINISTIC_DELAY_SECONDS="30", WORKER_LEASE_SECONDS=".8") as worker:
                for _ in range(100):
                    question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                    if question["attempt_count"] == number:
                        break
                    time.sleep(.05)
                else:
                    pytest.fail("Replacement attempt did not start")
                kill_process_tree(worker)
        with deployment.worker(WORKER_LEASE_SECONDS=".8"):
            failed = wait_for_question(client, conversation, "failed")
        assert failed["attempt_count"] == 3
        assert failed["deadline"] == accepted["deadline"]
        assert failed["last_error"] == "attempts_exhausted"
