# Evaluation

`scripts/evaluate.py` exercises only the public HTTP API. It records offered, accepted, completed, rejected, failed, expired and timed-out requests, plus complete-answer latency percentiles for each workload. Reports are JSON so they can be retained with the model, image, catalog release and resource settings used for a run.

Start the deployed stack and load a reviewed or load catalog, then run:

```sh
python scripts/evaluate.py --base-url http://127.0.0.1:8091 \
  --conversations 100 --questions 5 --workers 20 \
  --output artifacts/evaluation/real-vllm.json
```

Use a separate cache-cold run after deleting the semantic-cache collection, and a representative-cache run after warming it with the same workload. Run catalog description generation before this command; it is an offline job and must not share the interactive benchmark GPU budget.

For an outage scenario, stop the worker or inference container after requests are accepted, allow the maintenance/worker recovery path to settle, then rerun the same command and retain the report alongside `docker compose ps` and `/api/operations/questions/{id}` evidence. A completed answer counts only when the public question reaches `completed`; rejected and expired requests never count toward successful throughput. Compare `overall.complete_latency_p95_seconds` with the ten-second target and report the sustainable offered rate when the target is missed.
