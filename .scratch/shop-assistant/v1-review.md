# Shop assistant v1: accepted design

Status: Accepted on 2026-09-11 by confirmation of Q27, including the implementation defaults below. This is the implementation baseline, not a report of implemented or tested behavior.

## Scope and components

An anonymous shopper discovers, compares, and asks factual questions about a fixed synthetic product catalog. Use the five-department, ten-category hierarchy and unit-aware fields in [catalog-design.md](catalog-design.md). Accounts, checkout, payments, orders, live catalog updates, database failover, and administrator permissions are outside v1.

| Component | Responsibility |
| --- | --- |
| Basic browser UI | Conversation history, question submission, request status, cancellation, retry, product links |
| Replicated FastAPI processes | Validate submissions, durably accept questions, return status/results, serve product facts |
| Separate Python workers | Recoverable orchestration, retrieval, cache lookup, bounded model/tool calls |
| PostgreSQL | Conversations, request lifecycle, durable work queue, authoritative catalog facts, ingestion status |
| Qdrant | Product vectors and a separate semantic-cache collection |
| Local vLLM | Chat inference and offline synthetic description generation |
| CPU embedding service | Consistent embeddings for ingestion, retrieval and cache lookup, with distinct preprocessing where required |
| Independent batch jobs | Generate the fixture, validate it, ingest/recover it, enforce retention |
| OpenTelemetry, Prometheus, Tempo, Grafana | Request traces, metrics and linked operational dashboards |

Docker Compose is the first runnable deployment on this laptop, with persistent database volumes and multiple API/worker processes. Kubernetes manifests express the same components and independent scaling. Databases are assumed durable; application replica recovery is tested independently of storage failover.

## Request lifecycle

1. An opaque persistent browser cookie identifies the anonymous session. Only that session can retrieve its conversations; this does not require a shopper account. History is retained for 30 days, with expiry shown clearly rather than silently attaching old data to a new session.
2. The browser assigns a stable submission ID before sending. Within the session, an identical retry returns the same request. Reusing an ID with different content is rejected. There is one pending question per conversation.
3. Validate input size, per-session limits, and queue capacity before acceptance. Commit the request and its durable work record in PostgreSQL, then acknowledge. An uncertain connection/commit result is reconciled by retrying the same ID. Neither a Qdrant operation nor a cache write is part of this transaction.
4. Workers claim jobs with a renewable lease and attempt token. External service calls run outside the transaction. After a worker dies, another worker can reclaim the expired lease and repeat work.
5. The authoritative terminal states are completed, failed, cancelled, and expired. A conditional state-store update fences writes from obsolete workers. Cancellation and completion race through that update; the first valid terminal transition wins. Deadline checks use the stored acceptance time, not a restarted attempt's clock.
6. Persist the completed answer before showing it as completed. A browser disconnect does not cancel work. Explicit retry of a terminal failed/expired question creates a new submission ID; a transport retry retains the old one.
7. Show changing request status and then the durable complete answer. Token-by-token answer streaming is deferred. Polling is sufficient initially, with no browser affinity to a particular API process.

## Inference and overload policy

- Initial candidate: Qwen/Qwen3-1.7B through local vLLM, thinking disabled, validated tool calling. Use BAAI/bge-small-en-v1.5 on CPU for embeddings. See [model-research.md](model-research.md) for official sources, memory considerations, and candidate settings.
- Begin with a 4096-token model context, up to 512 output tokens per call, up to three model calls and two tool rounds per question. Count system instructions, tool schemas, retained conversation context and evidence against the context limit. Preserve full history durably but send only a bounded coherent subset to the model.
- Expose only read-only product-search and product-detail tools. Comparison uses facts from these tools. Validate arguments and numeric filters in application code. Treat catalog text as evidence, not as instructions to invoke arbitrary tools.
- Start with two global inference slots, adjustable after startup and measurement. Distinguish open conversations from active GPU sequences. Use shared durable coordination for slots, breaker state, and a single recovery probe; each replica's independent limiter cannot represent the global budget.
- Initial breaker defaults: open after five consecutive transient inference failures, pause calls for 15 seconds, then permit one probe. Honor server retry guidance. A successful probe closes the breaker; a failed probe reopens it. Validation and non-transient errors fail the request rather than tripping the overload breaker.
- Bound transient processing attempts to three, with jittered backoff, and keep every attempt within the accepted two-minute deadline. The model-call budget above applies to a successful processing attempt; retries can repeat lost work but never extend the request deadline. Bound total inference work per request as part of implementation tuning.
- A durable maintenance job expires waiting requests even while the breaker is open or no inference worker is healthy. Cancellation remains available while inference is down.
- Initial admission caps: 100 pending questions globally and one per conversation, with configurable session rate limiting. Reject excess submissions explicitly before acceptance. The cap bounds storage/work; it does not promise every accepted request succeeds before expiry.

## Ingestion and cache contracts

- Generate coherent structured product facts first, then use the local LLM for descriptions supported by those facts. Freeze the resulting dataset and manifest. Use approximately 300 reviewed products for quality tests and 100,000 varied products for load tests. Generate descriptions offline rather than competing with interactive inference during benchmarks.
- Each ingestion attempt reuses stable product IDs and a catalog release identifier. Independently upsert authoritative facts and Qdrant vectors, checkpoint progress, and verify required records before publishing the release as ready. An interrupted initial load is resumable; no partial release is served. Publication is coordinated across stores, not an atomic cross-store commit.
- Fetch current-for-this-fixed-release product facts before answering. Enforce category, price, stock, rating, dimensions, and weight using structured constraints. The ready release remains immutable for v1.
- Semantic cache is eligible only for standalone public questions. The conservative starting rule is first-turn questions only, with the same intent and explicit structured constraints. Similarity alone cannot prove equivalent meaning.
- Cache identity includes catalog release, locale, embedding/preprocessing, chat model, prompt, and tool-schema versions. Check referenced products and facts before answer reuse. Bypass a doubtful match. Keep product and cache vectors in separate collections.
- Commit each shopper's authoritative answer independently of cache insertion. Missing, failed, or partial cache writes become misses. Initial cache retention is 7 days with a configurable 10,000-entry cap and independent cleanup.

## Operator experience

A separate administration landing page links to Grafana and read-only request/ingestion status. No login or permissions are implemented. The status view shows identifiers, states, attempts, timings and errors; a separate raw-conversation inspection feature is deferred. Routine logs and traces omit raw prompts and answers.

Metrics cover admission/rejection, queue depth and age, lease recovery, completion/failure/expiry, breaker state, inference saturation/latency, retrieval latency, cache hit/miss/rejection, and ingestion progress. Trace identifiers connect admission to worker attempts, retrieval and model calls. Telemetry delivery failure must not lose or prevent a shopper answer. Traces are retained for 7 days; retention jobs also enforce the accepted 30-day conversation limit.

## Acceptance evidence

- Kill an API process after durable commit but before its response, then retry the same ID: exactly one request remains.
- Kill a worker during inference, recover it elsewhere, and verify at most one authoritative answer and no lost acknowledged question.
- Race completion against cancellation and expiry; obsolete workers cannot overwrite terminal state.
- Interrupt and resume ingestion; the fixed catalog becomes ready only after complete validation, without duplicate products.
- Disable or overload inference; verify bounded work, waiting/cancellation/expiry, coordinated probes, and recovery without a retry storm.
- Exercise cache near misses involving numerical limits, categories, intent, and follow-up context. Cache failures must not lose completed answers.
- Evaluate reviewed questions for relevant products, satisfied constraints, grounded claims, useful clarification, and valid product links. Report quality failures rather than hiding them behind latency results.
- Benchmark 100,000 products, 100 connected conversations, and a workload offered at five new questions per second. Include search, comparison, factual questions and follow-ups. Measure cache-cold and representative-cache traffic separately, publish all rejections/failures/expirations, and report end-to-end complete-answer p95 alongside successful throughput.
- The ten-second p95 remains the agreed target under normal load. Do not count rejection or expiry as a fast successful answer. The laptop's achievable operating point must be measured; no claim that its GPU meets the target is made by this design.

## Implementation verification

The design interview is complete. Model/image revision pinning, hardware startup, resource tuning, semantic thresholds and benchmark outcomes remain implementation work, not assumed facts. Repository skill setup is complete: root `AGENTS.md` points to the local Markdown tracker, default triage labels, and single-context domain rules in `docs/agents/`.
