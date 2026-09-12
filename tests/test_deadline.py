"""Exercise the real two-minute contract; no database edits or fake clock."""
import time
from uuid import uuid4


def test_late_inference_cannot_publish_after_original_deadline(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        accepted = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Question with an overdue answer",
        }).json()
        queued_conversation = client.post("/api/conversations").json()["id"]
        client.post(f"/api/conversations/{queued_conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Question that stays queued beyond its deadline",
        })
        # Deliberately non-cooperative inference returns a success after the deadline.
        with deployment.controlled_worker(TEST_INFERENCE_DELAY="121", TEST_INFERENCE_RESULT="Too late", WORKER_LEASE_SECONDS="2"):
            until = time.monotonic() + 135
            while time.monotonic() < until:
                question = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                assert question["status"] != "completed"
                if question["status"] == "expired":
                    queued = client.get(f"/api/conversations/{queued_conversation}").json()["questions"][-1]
                    if queued["status"] == "expired":
                        break
                time.sleep(.5)
            else:
                raise AssertionError("Deadline was not materialized after inference returned")
        assert question["deadline"] == accepted["deadline"]
        assert question["attempt_count"] == 1
        assert question["answer"] is None
        assert question["last_error"] == "deadline_exceeded"
        assert queued["status"] == "expired"
        assert queued["attempt_count"] == 0
