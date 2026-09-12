import time
from uuid import uuid4


def test_maintenance_expires_queued_work_without_inference_workers(deployment):
    with deployment.api() as client:
        client.post("/api/session")
        cookies = dict(client.cookies)
        conversation = client.post("/api/conversations").json()["id"]
        payload = {"submission_id": str(uuid4()), "text": "Expire this unanswered question"}
        path = f"/api/conversations/{conversation}/questions"
        accepted = client.post(path, json=payload).json()
        with deployment.maintenance() as maintenance:
            until = time.monotonic() + 135
            while time.monotonic() < until:
                assert maintenance.poll() is None, "Maintenance must be independently runnable"
                result = client.get(f"/api/conversations/{conversation}").json()["questions"][-1]
                if result["status"] == "expired":
                    break
                time.sleep(.5)
            else:
                raise AssertionError("Maintenance failed to expire the question")
        assert result["attempt_count"] == 0
        assert result["deadline"] == accepted["deadline"]
        assert result["terminal_at"] >= result["deadline"]
        assert result["answer"] is None
        assert client.post(path, json=payload).json() == result
        assert client.post(f"{path}/{accepted['id']}/cancel", json={}).json() == result
        retry = client.post(path, json={**payload, "submission_id": str(uuid4())})
        assert retry.status_code == 202
        assert retry.json()["id"] != result["id"]
        assert retry.json()["deadline"] > result["deadline"]
    with deployment.api() as reconnected:
        reconnected.cookies.update(cookies)
        assert reconnected.get(f"/api/conversations/{conversation}").json()["questions"][0] == result
