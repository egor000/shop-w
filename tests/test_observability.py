from uuid import uuid4


def test_operations_links_and_metrics_reflect_durable_question_state(deployment):
    with deployment.api() as client:
        assert client.get("/operations").status_code == 200
        page = client.get("/operations").text
        assert "/api/operations/summary" in page
        assert "http://localhost:3000" in page
        metrics_before = client.get("/metrics")
        assert metrics_before.status_code == 200
        assert "shop_telemetry_database_up 1" in metrics_before.text

        assert client.post("/api/session").status_code == 200
        conversation = client.post("/api/conversations").json()["id"]
        accepted = client.post(f"/api/conversations/{conversation}/questions", json={
            "submission_id": str(uuid4()), "text": "How much does the cup weigh?",
        })
        assert accepted.status_code == 202
        trace_id = accepted.headers["X-Trace-ID"]
        assert trace_id == accepted.headers["X-Request-ID"]
        summary = client.get("/api/operations/summary").json()
        assert summary["queue_depth"] == 1
        metrics_after = client.get("/metrics").text
        assert "shop_queue_depth 1" in metrics_after
        assert "shop_http_requests_total" in metrics_after
