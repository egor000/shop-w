from uuid import uuid4
import time
import pytest

from tests.conftest import process_tree, wait_for_question


def test_cancellation_is_saved_and_frees_conversation_for_another_question(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        cookies = dict(client.cookies)
        conversation = client.post("/api/conversations").json()["id"]
        payload = {"submission_id": str(uuid4()), "text": "Please describe the cup"}
        path = f"/api/conversations/{conversation}/questions"
        accepted = client.post(path, json=payload).json()
        cancelled = client.post(f"{path}/{accepted['id']}/cancel", json={})
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["answer"] is None
        assert cancelled.json()["terminal_at"] is not None
        assert client.post(path, json=payload).json() == cancelled.json()
        assert client.post(path, json={"submission_id": str(uuid4()), "text": "A different question"}).status_code == 202
    with deployment.api() as reconnected:
        reconnected.cookies.update(cookies)
        assert reconnected.get(f"/api/conversations/{conversation}").json()["questions"][0] == cancelled.json()


@pytest.mark.parametrize("winner", ["cancelled", "completed"])
def test_first_terminal_result_survives_late_completion_or_cancellation(deployment, winner):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        path = f"/api/conversations/{conversation}/questions"
        accepted = client.post(path, json={"submission_id": str(uuid4()), "text": "A terminal race"}).json()
        cancel_path = f"{path}/{accepted['id']}/cancel"
        with deployment.controlled_worker(TEST_INFERENCE_DELAY="2") as worker:
            if winner == "cancelled":
                wait_for_question(client, conversation, "processing")
                owners = process_tree(worker)
                for owner in owners:
                    owner.suspend()
                try:
                    terminal = client.post(cancel_path, json={}).json()
                finally:
                    for owner in reversed(owners):
                        owner.resume()
                time.sleep(2.5)
            else:
                terminal = wait_for_question(client, conversation, "completed")
            assert terminal["status"] == winner
            assert client.post(cancel_path, json={}).json() == terminal
            assert client.get(f"/api/conversations/{conversation}").json()["questions"] == [terminal]
            operations = client.get(f"/api/operations/questions/{accepted['id']}").json()
            assert operations["status"] == winner
            assert operations["terminal_at"] == terminal["terminal_at"]
            assert operations["attempts"][0]["outcome"] == winner


def test_other_sessions_cannot_cancel_a_question(deployment):
    with deployment.api() as owner, deployment.api() as stranger:
        owner.post("/api/session")
        stranger.post("/api/session")
        conversation = owner.post("/api/conversations").json()["id"]
        path = f"/api/conversations/{conversation}/questions"
        accepted = owner.post(path, json={"submission_id": str(uuid4()), "text": "Private question"}).json()
        assert stranger.post(f"{path}/{accepted['id']}/cancel", json={}).status_code == 404
        assert owner.get(f"/api/conversations/{conversation}").json()["questions"] == [accepted]
