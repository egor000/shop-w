"""Run reproducible public-API quality and capacity evaluations."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


WORKLOADS = {
    "discovery": "Find bluetooth headphones under $100",
    "factual": "What are the dimensions and weight of Aurora Headphones?",
    "constraint": "Find an unrated product under $50 that is in stock",
    "comparison": "Compare Aurora Headphones and Echo Portable Speaker",
    "followup": "What is its battery life?",
}


@dataclass
class Observation:
    workload: str
    accepted: bool
    completed: bool
    status: str
    offered_at: float
    terminal_at: float | None
    http_status: int
    error: str | None = None

    @property
    def latency_seconds(self) -> float | None:
        return None if self.terminal_at is None else self.terminal_at - self.offered_at


class PublicClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._local = threading.local()

    def call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode()
        cookie = getattr(self._local, "cookie", None)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        request = Request(self.base_url + path, data=data, method=method,
                          headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                self._remember_cookie(response.headers.get("Set-Cookie"))
                body = response.read()
                return response.status, json.loads(body) if body else {}
        except HTTPError as error:
            self._remember_cookie(error.headers.get("Set-Cookie"))
            body = error.read()
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {"detail": body.decode(errors="replace")}
            return error.code, parsed

    def _remember_cookie(self, header: str | None) -> None:
        if header:
            self._local.cookie = header.split(";", 1)[0]

    def conversation(self) -> str:
        status, _ = self.call("POST", "/api/session")
        if status >= 400:
            raise RuntimeError(f"session failed: HTTP {status}")
        status, body = self.call("POST", "/api/conversations")
        if status != 201:
            raise RuntimeError(f"conversation failed: HTTP {status}")
        return str(body["id"])

    def ask(self, conversation: str, text: str) -> tuple[int, dict]:
        return self.call("POST", f"/api/conversations/{conversation}/questions",
                         {"submission_id": str(uuid4()), "text": text})

    def wait(self, conversation: str, question_id: str) -> tuple[str, float]:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            status, body = self.call("GET", f"/api/conversations/{conversation}")
            if status >= 400:
                return "transport_error", time.time()
            for question in body.get("questions", []):
                if question.get("id") == question_id and question.get("status") in {"completed", "failed", "expired", "cancelled"}:
                    return str(question["status"]), time.time()
            time.sleep(.1)
        return "timeout", time.time()


def run_conversation(client: PublicClient, question_count: int) -> list[Observation]:
    conversation = client.conversation()
    observations: list[Observation] = []
    workload_names = list(WORKLOADS)
    for index in range(question_count):
        workload = workload_names[index % len(workload_names)]
        text = WORKLOADS[workload]
        offered = time.time()
        try:
            http_status, body = client.ask(conversation, text)
            if http_status != 202:
                observations.append(Observation(workload, False, False, "rejected", offered, None, http_status,
                                                str(body.get("detail", "rejected"))))
                continue
            status, terminal = client.wait(conversation, str(body["id"]))
            observations.append(Observation(workload, True, status == "completed", status, offered, terminal, http_status))
        except (OSError, ValueError, KeyError) as error:
            observations.append(Observation(workload, False, False, "transport_error", offered, None, 0, str(error)))
    return observations


def run_one(client: PublicClient, question_count: int) -> list[Observation]:
    offered = time.time()
    try:
        return run_conversation(client, question_count)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        return [Observation("conversation", False, False, "transport_error", offered, None, 0, str(error))]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)]


def summarize(observations: list[Observation], elapsed: float | None = None) -> dict:
    if elapsed is None and observations:
        elapsed = max(item.terminal_at or item.offered_at for item in observations) - min(item.offered_at for item in observations)
    elapsed = elapsed or 0
    latencies = [value for item in observations if (value := item.latency_seconds) is not None and item.completed]
    return {"observations": len(observations), "elapsed_seconds": elapsed,
            "offered_per_second": len(observations) / elapsed if elapsed else 0,
            "accepted": sum(item.accepted for item in observations),
            "completed": sum(item.completed for item in observations),
            "rejected": sum(not item.accepted for item in observations),
            "failures": sum(item.status in {"failed", "transport_error", "timeout"} for item in observations),
            "statuses": {status: sum(item.status == status for item in observations) for status in
                         sorted({item.status for item in observations})},
            "complete_latency_p50_seconds": percentile(latencies, .50),
            "complete_latency_p95_seconds": percentile(latencies, .95),
            "complete_latency_mean_seconds": statistics.mean(latencies) if latencies else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--conversations", type=int, default=100)
    parser.add_argument("--questions", type=int, default=5)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation/latest.json"))
    args = parser.parse_args()
    if min(args.conversations, args.questions, args.workers) < 1:
        parser.error("conversations, questions and workers must be positive")
    client = PublicClient(args.base_url, args.timeout)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        observations = [item for future in as_completed(pool.submit(run_one, client, args.questions) for _ in range(args.conversations))
                        for item in future.result()]
    elapsed = time.time() - started
    report = {"target": {"conversations": args.conversations, "questions_per_conversation": args.questions,
                         "p95_seconds": 10}, "workloads": {name: summarize([item for item in observations if item.workload == name])
                                                               for name in WORKLOADS}, "overall": summarize(observations, elapsed),
              "observations": [asdict(item) | {"latency_seconds": item.latency_seconds} for item in observations]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["overall"], sort_keys=True))


if __name__ == "__main__":
    main()
