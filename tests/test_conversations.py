"""Saved shopper answers through HTTP with a controlled external model service."""
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import pytest
import psycopg
from psycopg.types.json import Jsonb
from shop.catalog import CATALOG

from tests.conftest import wait_for_question
from tests.test_catalog import catalog_deployment


@contextmanager
def model_service(respond):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/tokenize":
                result = {"count": len(json.dumps(body).encode()) // 4, "max_model_len": 4096}
            else:
                result = {"choices": [{"message": respond(body), "finish_reason": "stop"}]}
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def tool(name, arguments):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "call_1", "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }]}


def submit(client, conversation, text):
    response = client.post(f"/api/conversations/{conversation}/questions", json={
        "submission_id": str(uuid4()), "text": text})
    assert response.status_code == 202
    return wait_for_question(client, conversation, "completed")


def test_comparison_saves_both_products_and_authoritative_shared_facts(catalog_deployment):
    deployment, _, _ = catalog_deployment

    def respond(body):
        if body["messages"][-1]["role"] != "tool":
            return tool("product_details", {"references": ["Aurora Headphones", "Echo Portable Speaker"]})
        return {"content": json.dumps({"text": "Compare their recorded product facts.", "products": []})}

    with model_service(respond) as url, deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=url):
            answer = submit(client, conversation, "Compare Aurora Headphones and Echo Portable Speaker")["answer"]
        assert [product["url"] for product in answer["products"]] == [
            "/products/aurora-headphones", "/products/echo-speaker"]
        assert "USD 89.99" in answer["text"]
        assert "USD 54.99" in answer["text"]
        assert "0.31 kg" in answer["text"]
        assert "0.52 kg" in answer["text"]
        assert "18 × 16 × 8 cm" in answer["text"]
        assert "not recorded" in answer["text"].lower()


def test_followup_preserves_structured_constraints_after_worker_restart(catalog_deployment):
    deployment, _, _ = catalog_deployment

    def respond(body):
        if body["messages"][-1]["role"] == "tool":
            return {"content": json.dumps({"text": "These products satisfy your constraints.", "products": []})}
        current = [message["content"] for message in body["messages"] if message["role"] == "user"][-1]
        constraints = {} if current.startswith("What") else {
            "category": "Headphones", "max_price_cents": 9000, "min_rating": 4.3,
            "max_length_cm": 20, "max_width_cm": 17, "max_height_cm": 10,
            "max_weight_kg": .35, "attributes": {"connection": "bluetooth"},
        }
        return tool("search_products", {"query": "waterproof bluetooth", "constraints": constraints})

    with model_service(respond) as url, deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=url):
            first = submit(client, conversation, "Find headphones under $90, rated at least 4.3, under 20 by 17 by 10 cm, under .35 kg with bluetooth")
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=url):
            followup = submit(client, conversation, "What is their battery life with the same requirements?")
        assert [p["url"] for p in first["answer"]["products"]] == ["/products/aurora-headphones"]
        assert [p["url"] for p in followup["answer"]["products"]] == ["/products/aurora-headphones"]
        assert len(client.get(f"/api/conversations/{conversation}").json()["questions"]) == 2


def test_long_conversation_keeps_full_history_and_stays_inside_model_window(catalog_deployment):
    deployment, _, _ = catalog_deployment

    def respond(body):
        if len(json.dumps({key: body[key] for key in ("model", "messages", "tools")}).encode()) // 4 > 3584:
            return {"content": json.dumps({"text": "Context window exceeded", "products": []})}
        if body["messages"][-1]["role"] == "tool":
            return {"content": json.dumps({"text": "The recorded headphones weigh 0.31 kg.", "products": []})}
        return tool("product_details", {"references": ["Aurora Headphones"]})

    with model_service(respond) as url, deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        texts = ["Tell me about Aurora Headphones. " + ("Travel context. " * 210) for _ in range(6)]
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=url):
            for text in texts:
                result = submit(client, conversation, text)
                assert "The recorded headphones weigh 0.31 kg." in result["answer"]["text"]
        history = client.get(f"/api/conversations/{conversation}").json()["questions"]
        assert [question["text"] for question in history] == texts


def test_unresolved_followup_in_another_session_asks_for_product_identity(catalog_deployment):
    deployment, _, _ = catalog_deployment

    def respond(body):
        if body["messages"][-1]["role"] == "tool":
            return {"content": json.dumps({"text": "Aurora weighs 0.31 kg.", "products": []})}
        return tool("product_details", {"references": ["Aurora Headphones"]})

    with model_service(respond) as url, deployment.api() as owner, deployment.api() as stranger:
        owner.post("/api/session")
        stranger.post("/api/session")
        owned = owner.post("/api/conversations").json()["id"]
        separate = stranger.post("/api/conversations").json()["id"]
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=url):
            submit(owner, owned, "Tell me about Aurora Headphones")
            result = submit(stranger, separate, "What is its weight?")
        assert result["answer"]["products"] == []
        assert "which product" in result["answer"]["text"].lower()
        assert stranger.get(f"/api/conversations/{owned}").status_code == 404


def test_overlapping_names_clarify_without_losing_previous_constraints(catalog_deployment):
    deployment, _, _ = catalog_deployment
    # Fixture setup only; every assertion observes the application response.
    facts = CATALOG[0].facts() | {"id": "aurora-pro", "name": "Aurora Headphones Pro", "price_cents": 12999}
    with psycopg.connect(deployment.env["DATABASE_URL"], options=deployment.env["PGOPTIONS"]) as db:
        db.execute("INSERT INTO products(id, facts) VALUES (%s, %s)", ("aurora-pro", Jsonb(facts)))

    def respond(body):
        if body["messages"][-1]["role"] == "tool":
            return {"content": json.dumps({"text": "Here are the recorded facts.", "products": []})}
        current = [message["content"] for message in body["messages"] if message["role"] == "user"][-1]
        if current.startswith("Compare"):
            return tool("product_details", {"references": ["Aurora", "Echo Portable Speaker"]})
        constraints = {"category": "Headphones", "max_price_cents": 9000} if current.startswith("Find") else {}
        return tool("search_products", {"query": "bluetooth", "constraints": constraints})

    with model_service(respond) as url, deployment.api() as client:
        client.post("/api/session")
        conversation = client.post("/api/conversations").json()["id"]
        with deployment.worker(INFERENCE_BACKEND="vllm", VLLM_URL=url):
            submit(client, conversation, "Find headphones under $90")
            ambiguous = submit(client, conversation, "Compare Aurora and Echo Portable Speaker")
            result = submit(client, conversation, "Keep the same requirements and find bluetooth products")
        assert "which product" in ambiguous["answer"]["text"].lower()
        assert {p["url"] for p in ambiguous["answer"]["products"]} == {"/products/aurora-headphones", "/products/aurora-pro"}
        assert [p["url"] for p in result["answer"]["products"]] == ["/products/aurora-headphones"]
