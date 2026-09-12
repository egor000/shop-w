from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytest

from conftest import wait_for_question


def test_accepted_question_survives_api_restart_and_worker_saves_answer(deployment):
    with deployment.api() as client:
        assert client.post("/api/session").status_code == 200
        cookies = dict(client.cookies)
        conversation = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "How much does the Trail Cup weigh?",
        })
        assert response.status_code == 202
        question = response.json()
        assert question["status"] == "waiting"
        assert question["answer"] is None

    with deployment.api() as reconnected:
        reconnected.cookies.update(cookies)
        assert reconnected.get(f"/api/conversations/{conversation}").json()["questions"] == [question]
        with deployment.worker():
            processing = wait_for_question(reconnected, conversation, "processing")
            assert processing["answer"] is None
            answer = wait_for_question(reconnected, conversation, "completed")
        assert "0.25 kg" in answer["answer"]["text"]
        assert answer["id"] == question["id"]
        link = answer["answer"]["products"][0]["url"]
        product = reconnected.get(link)
        assert product.status_code == 200
        assert "Trail Cup" in product.text
        assert "0.25 kg" in product.text

    with deployment.api() as refreshed:
        refreshed.cookies.update(cookies)
        assert refreshed.get(f"/api/conversations/{conversation}").json()["questions"] == [answer]


def test_concurrent_transport_retries_preserve_one_question_and_original_deadline(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        path = f"/api/conversations/{conversation}/questions"
        payload = {"submission_id": str(uuid4()), "text": "Tell me about the Trail Cup"}
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: client.post(path, json=payload), range(6)))
        assert all(response.status_code == 202 for response in responses)
        question = responses[0].json()
        assert all(response.json() == question for response in responses)
        assert (datetime.fromisoformat(question["deadline"]) - datetime.fromisoformat(question["accepted_at"])).total_seconds() == 120
        changed = client.post(path, json={**payload, "text": "Different question"})
        assert changed.status_code == 409
        assert client.get(f"/api/conversations/{conversation}").json()["questions"] == [question]
        with deployment.worker():
            completed = wait_for_question(client, conversation, "completed")
        assert client.post(path, json=payload).json() == completed


def test_only_one_pending_question_is_accepted_under_concurrent_submissions(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        path = f"/api/conversations/{conversation}/questions"
        with ThreadPoolExecutor(max_workers=5) as pool:
            responses = list(pool.map(lambda _: client.post(path, json={
                "submission_id": str(uuid4()), "text": "How big is the cup?",
            }), range(5)))
        assert sorted(response.status_code for response in responses) == [202, 409, 409, 409, 409]
        assert len(client.get(f"/api/conversations/{conversation}").json()["questions"]) == 1
        with deployment.worker():
            wait_for_question(client, conversation, "processing")
            assert client.post(path, json={"submission_id": str(uuid4()), "text": "Another question"}).status_code == 409
            wait_for_question(client, conversation, "completed")
        assert client.post(path, json={"submission_id": str(uuid4()), "text": "Another question"}).status_code == 202


@pytest.mark.parametrize("text", ["", "   \n\t", "x" * 4001, None, 42, "Question\u0000"])
def test_invalid_question_is_rejected_before_acceptance(deployment, text):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": text,
        })
        assert response.status_code == 422
        assert client.get(f"/api/conversations/{conversation}").json()["questions"] == []


def test_anonymous_sessions_are_persistent_and_cannot_access_each_other(deployment):
    with deployment.api() as owner, deployment.api() as stranger:
        assert owner.post("/api/conversations").status_code == 401
        established = owner.post("/api/session")
        cookie = established.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Max-Age=" in cookie and "SameSite=strict" in cookie
        before = dict(owner.cookies)
        owner.post("/api/session")
        assert dict(owner.cookies) == before
        conversation = owner.post("/api/conversations").json()["id"]
        stranger.post("/api/session")
        assert dict(stranger.cookies) != before
        assert stranger.get(f"/api/conversations/{conversation}").status_code == 404
        assert stranger.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "Intruder",
        }).status_code == 404
        assert owner.get(f"/api/conversations/{conversation}").json()["questions"] == []


@pytest.mark.parametrize("payload", [
    {"submission_id": "not-a-uuid", "text": "Question"},
    {"text": "Question"},
    {"submission_id": str(uuid4()), "text": "Question", "unexpected": True},
])
def test_invalid_submission_envelope_is_not_accepted(deployment, payload):
    with deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        assert client.post(f"/api/conversations/{conversation}/questions", json=payload).status_code == 422
        assert client.get(f"/api/conversations/{conversation}").json()["questions"] == []
