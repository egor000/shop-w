"""Exercise running processes over HTTP against a dedicated real PostgreSQL DB."""
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
import pytest
import psycopg
from psycopg import sql
from uuid import uuid4


@contextmanager
def process(*args, env):
    child = subprocess.Popen([sys.executable, *args], env=env)
    try:
        yield child
    finally:
        child.terminate()
        child.wait(timeout=10)


class Deployment:
    def __init__(self):
        self.env = {**os.environ, "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://shop:shop-test@127.0.0.1:55439/shop_test",
        ), "DETERMINISTIC_DELAY_SECONDS": "1"}

    @contextmanager
    def api(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with process("-m", "uvicorn", "shop.api:app", "--port", str(port),
                     "--no-access-log", env=self.env) as child:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                for _ in range(100):
                    assert child.poll() is None, "API process exited"
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("API did not become ready")
                yield client

    def worker(self):
        return process("-m", "shop.worker", env=self.env)


@pytest.fixture(scope="session")
def deployment():
    deployment = Deployment()
    # Isolate runs without clearing any pre-existing application data.
    schema = "test_" + uuid4().hex
    with psycopg.connect(deployment.env["DATABASE_URL"]) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    deployment.env["PGOPTIONS"] = f"-c search_path={schema}"
    try:
        subprocess.run([sys.executable, "-m", "shop.migrate"], env=deployment.env, check=True)
        yield deployment
    finally:
        with psycopg.connect(deployment.env["DATABASE_URL"]) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def wait_for_question(client, conversation, status):
    for _ in range(100):
        response = client.get(f"/api/conversations/{conversation}")
        assert response.status_code == 200
        questions = response.json()["questions"]
        if questions and questions[-1]["status"] == status:
            return questions[-1]
        time.sleep(0.1)
    pytest.fail(f"Question did not reach {status}: {questions}")
