# Shop assistant v1

Status: ready-for-agent

The product design, implementation baseline, and testing boundaries are accepted. Published to the local Markdown issue tracker.

## Problem Statement

Shoppers need help finding suitable products, comparing alternatives, and understanding product facts without manually navigating a large catalog. A useful answer must respect constraints such as price, rating, dimensions, and weight, and make it easy to inspect the supporting products.

A chat interaction also needs predictable behavior when processing is slow, inference is overloaded, the browser disconnects, or an application process dies. Shoppers must be able to distinguish an accepted question from a rejected submission and recover the status or result of accepted work. Operators need enough visibility to explain delays and failures and recover interrupted ingestion.

The first version must demonstrate these behaviors on a fixed fictional catalog with locally hosted inference and a basic interface, while retaining an architecture that supports multiple application replicas.

## Solution

Provide an anonymous shopping assistant for product discovery, product comparison, and factual questions. It uses read-only catalog tools, grounds product claims in catalog facts, includes local product links, and asks for clarification or explains missing information when necessary.

Persist accepted questions and completed answers independently of the browser connection. Display request status while work is pending, allow cancellation, and provide clear retry behavior after failures or expiry. Recover interrupted processing without creating duplicate authoritative answers. Bound queued work and inference activity so overload produces visible waiting or rejection rather than unbounded retries.

Generate a reproducible synthetic catalog across a simple hierarchy, then ingest it through independent, resumable jobs. Use PostgreSQL for durable application state and authoritative product facts, Qdrant for vector retrieval and semantic caching, local vLLM for chat inference, and CPU embeddings. Provide separate operational pages and Grafana dashboards backed by metrics and traces.

## User Stories

1. As a shopper, I want to describe what I need in ordinary language, so that I can discover suitable products without knowing exact product names.
2. As a shopper, I want to search within a department, so that I can consider products from its related categories.
3. As a shopper, I want to restrict a question to a category, so that unrelated products do not appear as matches.
4. As a shopper, I want price constraints to be respected, so that suggested products fit my budget.
5. As a shopper, I want to ask about stock and availability, so that I understand which products are available in the demonstration catalog.
6. As a shopper, I want to filter by rating, so that I can choose products meeting my preferences.
7. As a shopper, I want to see rating counts and identify unrated products, so that a missing rating is not presented as a real score.
8. As a shopper, I want to constrain product dimensions, so that recommended products fit the space I have available.
9. As a shopper, I want to constrain product weight, so that I can choose products suitable for carrying or handling.
10. As a shopper, I want category-specific attributes to be considered, so that suggestions reflect relevant properties such as capacity, brightness, or battery life.
11. As a shopper, I want to ask factual questions about a named product, so that I can understand its recorded specifications.
12. As a shopper, I want products with similar names to be distinguished, so that the assistant answers about the intended product.
13. As a shopper, I want to compare products using common units and attributes, so that their differences are easy to assess.
14. As a shopper, I want unavailable or inapplicable attributes to be identified, so that comparisons do not invent missing facts.
15. As a shopper, I want links to the products discussed in an answer, so that I can inspect their details.
16. As a shopper, I want clarification when my request is ambiguous, so that the assistant can narrow its search.
17. As a shopper, I want an honest explanation when no suitable product or supporting fact is found, so that I am not misled by an invented answer.
18. As a shopper, I want to ask follow-up questions in a conversation, so that I can refine an earlier request without starting over.
19. As a shopper, I want to use the assistant without creating an account, so that I can begin immediately.
20. As a shopper, I want my conversation to survive a browser refresh or reconnect, so that I can return to accepted work.
21. As a shopper, I want my anonymous session's conversations kept separate from other sessions, so that another shopper's history does not appear in mine.
22. As a shopper, I want acknowledgement only after my question is saved, so that acceptance has a reliable meaning.
23. As a shopper, I want a repeated submission caused by a connection retry to refer to the original question, so that I do not receive duplicate processing results.
24. As a shopper, I want clear validation errors before acceptance, so that I can correct an invalid or oversized submission.
25. As a shopper, I want to see whether a question is waiting, processing, completed, failed, cancelled, or expired, so that I know what happened to it.
26. As a shopper, I want the assistant to recover after an application worker crashes, so that an accepted question is not silently abandoned.
27. As a shopper, I want only one authoritative completed answer per question, so that repeated internal attempts do not produce conflicting results.
28. As a shopper, I want to cancel a pending question, so that I can stop waiting and submit another.
29. As a shopper, I want a clear limit of one pending question per conversation, so that the order of questions and answers remains understandable.
30. As a shopper, I want expired requests to remain visible with their outcome, so that a deadline does not make the request disappear.
31. As a shopper, I want to retry a failed or expired question explicitly, so that I can try again when service has recovered.
32. As a shopper, I want overload rejection to be clearly distinguished from acceptance, so that I know whether the system has taken responsibility for my question.
33. As a shopper, I want waiting and cancellation to work during inference outages, so that temporary model unavailability does not make the interface unusable.
34. As a shopper, I want to see the saved complete answer when it is ready, so that a connection interruption cannot make a partial answer appear final.
35. As a shopper, I want cached responses to respect my current question and constraints, so that a similar question does not receive an unsuitable answer.
36. As a shopper, I want history-dependent questions to be answered in my own context, so that cached answers from other conversations do not substitute for that context.
37. As a shopper, I want conversation retention and expiry to be clear, so that I understand when old history is no longer available.
38. As an operator, I want a small, coherent fictional catalog for demonstrations and quality evaluation, so that expected answers can be reviewed.
39. As an operator, I want a separate varied catalog of 100,000 products, so that retrieval and processing can be evaluated at the design scale.
40. As an operator, I want product generation to start from structured facts, so that generated descriptions can be checked for unsupported claims.
41. As an operator, I want a frozen catalog artifact with stable identities and a manifest, so that repeated ingestion uses the same input.
42. As an operator, I want ingestion to run independently of the application, so that loading the catalog does not depend on a browser interaction.
43. As an operator, I want interrupted ingestion to resume safely, so that an application or job interruption does not require discarding successful work.
44. As an operator, I want catalog readiness to require complete validated facts and vectors, so that shoppers do not search an incomplete initial release.
45. As an operator, I want partial writes across PostgreSQL and Qdrant to be recoverable, so that correctness does not depend on a transaction spanning both stores.
46. As an operator, I want failed cache insertion to leave completed answers intact, so that an optimization cannot lose shopper work.
47. As an operator, I want configurable queue and inference limits shared across replicas, so that adding workers does not accidentally overload the model.
48. As an operator, I want coordinated circuit-breaker recovery probes, so that inference recovery does not trigger a retry storm.
49. As an operator, I want request attempts and deadlines to remain bounded across restarts, so that failed work cannot run indefinitely.
50. As an operator, I want status and ingestion pages separate from the shopper interface, so that operational information is easy to find.
51. As an operator, I want metrics for admission, queueing, recovery, retrieval, caching, and inference, so that I can locate bottlenecks and failures.
52. As an operator, I want traces to connect acceptance with worker attempts and dependency calls, so that I can investigate a request's path through the system.
53. As an operator, I want routine telemetry to omit raw conversation text, so that diagnostics use operational metadata.
54. As an operator, I want telemetry outages to leave shopper processing functional, so that monitoring does not become a required step in answering.
55. As an operator, I want automated conversation, trace, and cache retention, so that retained data remains bounded.
56. As a developer, I want a Docker Compose deployment with local vLLM on this machine, so that I can run and investigate the system locally.
57. As a developer, I want Kubernetes deployment definitions for the same components, so that application replicas can later run across pods.
58. As a developer, I want model and dependency revisions pinned, so that a measured setup can be reproduced.
59. As a developer, I want repeatable failure scenarios at the application's public boundary, so that recovery behavior can be verified without depending on model randomness.
60. As a developer, I want real-model quality and performance measurements reported separately from deterministic tests, so that passing a substitute-based test is not mistaken for a working inference deployment.

## Implementation Decisions

1. **Application shape.** Build a Python/FastAPI application with independently running Python workers, a basic HTML/JavaScript shopper interface, product-detail views, and an operational landing/status interface. API replicas share durable state and require no browser affinity.
2. **Logical modules.** Keep request lifecycle and recovery, shopping orchestration, catalog ingestion/retrieval, semantic caching, and observability behind small interfaces. The public application and job interfaces are the principal integration boundaries. No existing application modules or APIs need migration.
3. **Persistence ownership.** PostgreSQL owns anonymous conversations, shopper questions, terminal results, durable work records, authoritative product facts, and ingestion state. Qdrant owns product vectors and a separate semantic-cache collection. Cross-store operations must tolerate partial completion and retries.
4. **Durable acceptance.** Save a question and its work record together in PostgreSQL before acknowledging acceptance. Qdrant access, model calls, embeddings, and cache writes are outside that transaction. A lost acknowledgement is an uncertain outcome reconciled through the original submission identifier.
5. **Session identity.** Use an opaque persistent browser cookie for the anonymous session. Scope conversation retrieval and submission identifiers to that session. Shopper accounts and cross-device identity are unnecessary for v1; lack of administrator authentication does not remove shopper-session isolation.
6. **Public contracts.** Support starting and reading conversations, submitting a question with a stable identifier, obtaining durable status/result, cancelling pending work, and reading product details. Return explicit distinctions between accepted work, invalid input, conflicting identifier reuse, unavailable capacity, and missing or expired history. Exact route names and internal type names remain implementation choices.
7. **Submission deduplication.** An identical transport retry in the same session resolves to the existing question before considering admission of new work. Reusing an identifier with different content is rejected. Explicitly retrying a terminal failed or expired question uses a new identifier. Browser disconnects do not cancel accepted work.
8. **Conversation ordering.** Allow one pending question per conversation. A shopper can cancel it before submitting another. Preserve full conversation history for retention while selecting a bounded coherent subset for inference.
9. **Work ownership.** Workers claim durable work using renewable leases and attempt tokens. Release database transactions before external calls. Reclaim abandoned work after a lease expires, and prevent an obsolete attempt from publishing an authoritative result.
10. **Terminal state.** Completed, failed, cancelled, and expired are terminal outcomes. Use a conditional persistent transition to choose the first valid terminal outcome. Cancellation/completion races cannot overwrite an existing terminal result, and every completion checks current ownership and the original deadline.
11. **Answer delivery.** Save the complete answer before presenting it as completed. The UI polls durable status, then displays the saved answer. Token-by-token answer streaming is deferred.
12. **Admission and expiry.** Start with 100 pending questions globally and one per conversation, plus configurable session rate and input-size limits. Enforce limits consistently across API replicas. A request has a two-minute lifetime from acceptance including waiting and retries. A separate maintenance job materializes expiry even when inference workers are unavailable.
13. **Bounded retries.** Allow at most three transient processing attempts with jittered backoff, inside the original deadline. Retries may repeat internal work without extending that deadline. Persist or otherwise durably enforce the finite attempt and inference-work budgets so restarts cannot reset them.
14. **Global inference control.** Start with two active inference slots across all workers, adjustable from measured capacity. Coordinate slot ownership, breaker state, and recovery probes using shared durable state. Recover coordination ownership after process failure; adding replicas must not multiply the configured inference budget.
15. **Circuit breaker.** Initially open after five consecutive transient inference failures, wait 15 seconds, and allow one recovery probe. Close on probe success and reopen on probe failure. Honor server retry guidance. Input validation and permanent request errors terminate the affected work without treating them as shared inference overload.
16. **Local inference.** Deploy vLLM on the development laptop under its Linux Docker/WSL2 runtime. The initial chat candidate is Qwen3-1.7B with thinking disabled and validated tool calling. Validate actual GPU-container visibility, startup, memory use, and answer quality before declaring the configuration usable.
17. **Inference budgets.** Begin with a 4096-token context, up to 512 generated tokens per model call, up to three orchestration model calls and two tool rounds per processing attempt, and the bounded retry policy above. Budget instructions, tool definitions, evidence, conversation context, and output together. These are initial limits to tune and record without weakening the finite-lifetime contract.
18. **Embeddings.** Initially use BAAI/bge-small-en-v1.5 on CPU to preserve GPU capacity. Use the same pinned model and product-retrieval preprocessing for ingestion and queries. Keep semantic-cache question preprocessing explicitly identified and separate from product-retrieval preprocessing. Bound embedding batches and interactive resource use.
19. **Tools and grounding.** Expose read-only product search and product-detail tools. Validate tool arguments in application code and treat retrieved catalog text as evidence. Generate comparisons from recorded facts, provide product links, clarify ambiguous requests, and identify absent or inapplicable information rather than inventing it.
20. **Fixed catalog.** V1 uses an immutable synthetic catalog in English with USD prices and independent products without variant families. Availability and prices mean the values in the fixed published release, not live shop inventory or pricing.
21. **Hierarchy.** A department contains categories, and each product belongs to one leaf category. Department filtering includes its children. Stable category identifiers are independent of display names.
22. **Department/category mapping.** Electronics contains Headphones and Portable speakers; Home contains Electric kettles and Table lamps; Office contains Keyboards and Desk organizers; Sports contains Yoga mats and Dumbbells; Outdoors contains Backpacks and Camping lanterns.
23. **Shared product facts.** Store stable product identity, fictional name/brand, department/category identity, description, typed category attributes, price in integer USD cents, nonnegative stock, derived availability, rating average and count, product dimensions, product weight, and a local detail link. Unrated products have zero count and no average.
24. **Units and attributes.** Product dimensions use centimeters and product weight uses kilograms, excluding shipping packaging. Record the measurement configuration where relevant. Category attributes include connection/battery properties, kettle capacity, lamp brightness/dimmability, keyboard layout, organizer compartments, mat thickness, dumbbell adjustment/piece count, backpack capacity, and lantern runtime.
25. **Filtering correctness.** Apply category, price, stock, rating, dimensions, weight, and supported category-attribute constraints to structured values. Semantic similarity cannot relax an explicit numerical or category constraint. Comparisons use compatible units and explain unavailable facts.
26. **Synthetic generation.** Generate coherent structured facts using a fixed seed and category-appropriate ranges, then use the local LLM to produce descriptions grounded in those facts. Validate and freeze results with a schema/generator version, record count, and checksum. Ingestion restarts reuse the frozen descriptions rather than regenerating them.
27. **Fixtures.** Maintain approximately 300 reviewed products across the ten categories for quality evaluation and a separate varied 100,000-product fixture for load evaluation. Include out-of-stock and unrated products, near matches with different constraints, and overlapping names. Use local product pages and placeholder artwork without runtime dependence on an external dataset or image host.
28. **Resumable ingestion.** Independent jobs use stable product identifiers and a catalog release identifier to upsert facts and vectors in retryable batches, checkpoint progress, and verify consistency/completeness. Publish the release as ready only after required facts and vectors are validated. Partial initial loads are not served.
29. **Publication across stores.** Catalog readiness coordinates independently completed PostgreSQL and Qdrant writes. No distributed transaction is assumed. A failed job resumes or reconciles its partial progress; repeated execution does not duplicate logical products.
30. **Semantic-cache eligibility.** Initially restrict reuse to standalone public first-turn questions with matching intent and explicit structured constraints. Exclude history-dependent and personalized requests. Similarity alone is insufficient, and uncertain matches are bypassed.
31. **Cache compatibility.** Include catalog release, locale, embedding/preprocessing identity, chat-model identity, prompt identity, and tool-schema identity in compatibility checks. Validate referenced products and fetch authoritative facts, including price and availability, before saving a reused answer for the current question.
32. **Cache failure and retention.** Persist the authoritative answer independently of cache insertion. Failed, absent, partial, incompatible, or expired cache records become misses. Start with seven-day cache retention and a configurable 10,000-entry cap with independent cleanup.
33. **Operational interface.** Provide separate links to Grafana and read-only request/ingestion status. Show identifiers, states, attempts, timings, and errors. V1 has no administrator authentication or permissions, and a raw-conversation inspection feature is deferred.
34. **Observability.** Instrument the application and jobs with OpenTelemetry, store metrics in Prometheus and traces in Tempo, and visualize them in Grafana. Cover admission/rejection, queue depth/age, lease recovery, terminal outcomes, breaker state, inference saturation/latency, retrieval timing, cache decisions, and ingestion progress.
35. **Trace and logging behavior.** Correlate acceptance with worker attempts and retrieval/model calls through identifiers. Routine logs and traces omit raw prompts and answers. Telemetry delivery failures must not prevent saving or serving answers.
36. **Retention.** Retain conversations for 30 days and traces for seven days, with maintenance enforcing removal/expiry and a clear expired-history experience. Cache lifecycle is independent of conversation retention.
37. **Deployment.** Deliver Docker Compose for the first runnable local deployment, with persistent database volumes and multiple API/worker processes, and Kubernetes definitions for the same independently scalable components. Provision local vLLM as part of v1.
38. **Failure scope.** Assume PostgreSQL and Qdrant provide adequate durability. Test loss/restart of application replicas and worker processes while durable dependencies remain available. Inference may be unavailable during recovery; accepted work remains subject to its deadline.
39. **Reproducibility.** Pin application dependencies, container images, model/tokenizer revisions, embedding revision, and relevant preprocessing/tool configuration during implementation. Run bulk description generation separately from interactive inference benchmarking.
40. **Capacity target.** Design for a 100,000-product catalog, 100 concurrent conversations, and five newly offered questions per second, with a target of complete answers within ten seconds at p95 under normal load. The two local inference slots and queue size are starting settings, not demonstrated support for that target.

## Testing Decisions

The user confirmed the testing boundaries below: public application and ingestion-job interfaces with real PostgreSQL and Qdrant, controllable inference/embedding substitutes for repeatable failure scenarios, and separate real local model runs for quality and performance.

1. **Highest shared boundary.** Exercise the running application's public contracts: submit, inspect status, reconnect, cancel, retry, and read product facts. Use the same externally observed system for recovery, cache, filtering, and overload scenarios rather than exposing a new test-only interface for every internal module.
2. **Job entry points.** Drive generation/validation, ingestion, and retention through their supported job interfaces. Observe catalog readiness and product availability through the application's public interface, and observe job status through the operational interface. This is the small additional entry point needed for work that intentionally runs outside shopper requests.
3. **Real persistence.** Use real disposable PostgreSQL and Qdrant instances for integration and process-recovery tests. Verify outcomes after process restart or reconnect. In-memory persistence substitutes cannot establish transaction, lease, or cross-store recovery behavior.
4. **Controllable inference.** Use deterministic inference and embedding substitutes at dependency boundaries for repeatable timeout, overload, malformed output, delayed completion, and failure scenarios. Keep a separate real local vLLM/embedding suite for startup, tool compatibility, retrieval quality, answer quality, and performance.
5. **Good-test standard.** Assert public status, final answers, product constraints, isolation, durable recovery, published catalog contents, and emitted operational signals. Avoid assertions about private helper calls, exact SQL text, internal object layouts, or a fixed order of calls unless that order is externally contractual.
6. **Covered modules.** Cover request lifecycle/recovery, shopping orchestration, catalog generation/ingestion/retrieval, semantic-cache eligibility/reuse, shared inference admission/breaker behavior, retention, operational signals, and the browser's basic interaction flow through those high-level boundaries.
7. **Prior art.** The repository currently contains skills, accepted design documents, a domain glossary, and ADRs, but no application code or existing test suite. There are no existing application seams or test conventions to reuse.
8. **Acknowledgement ambiguity.** Kill an API process after commit and before acknowledgement, then retry through another replica with the same identifier. Observe one logical question and one eventual terminal outcome. Check that changed content with the same identifier is rejected.
9. **Worker recovery.** Kill a worker during inference, allow another worker to recover the job, and verify that the accepted question remains accessible and at most one authoritative answer appears. A late obsolete worker response cannot replace the result.
10. **Terminal races.** Deterministically race completion with cancellation and expiry. Check that the first valid terminal transition wins, the original deadline is honored across attempts, and restarting workers cannot reset the attempt budget.
11. **Sessions and conversation order.** Verify same-browser recovery, isolation between anonymous sessions, one pending question per conversation, explicit retry with a new identifier, transport retry with the existing identifier, and retention expiry.
12. **Admission and overload.** Drive multiple API/worker replicas past configured limits. Observe bounded accepted work, explicit pre-acceptance rejection, a global inference cap, coordinated probes, waiting/cancellation/expiry during an outage, and recovery without a retry storm.
13. **Ingestion interruption.** Interrupt jobs between facts and vector writes and during later batches. Resume through the job entry point and verify no partial release becomes ready, no duplicate logical products appear, and the validated complete catalog becomes searchable.
14. **Catalog and grounding.** Use reviewed expected facts to test all ten categories, department expansion, unit-aware constraints, rating nullability, stock, near-identical names, comparisons, clarification, absent facts, and valid product links.
15. **Cache correctness.** Exercise eligible paraphrases alongside near misses in intent, numeric limits, categories, versions, product references, and conversation context. Verify bypass/recomputation for incompatible or doubtful entries and successful answer retention despite cache-insertion failure.
16. **Browser coverage.** Keep a small real-browser suite for session persistence, submission and status display, complete-answer rendering, cancellation/retry, history expiry, product links, and separate operational links. It complements the shared API suite rather than duplicating every fault case.
17. **Telemetry and retention.** Assert that supported metrics/traces identify acceptance, attempts, retrieval, inference, and cache outcomes without raw chat text. Observe continued shopper processing when telemetry delivery fails. Verify retention through external availability/status and supported telemetry storage queries.
18. **Real-model evaluation.** Verify the pinned model starts with available GPU memory, emits usable tool calls, handles tool results and malformed requests, and produces grounded answers. Run actual embedding/retrieval and model evaluation on the reviewed fixture; report relevance, satisfied constraints, unsupported claims, clarification quality, and tool failures.
19. **Load evidence.** Use the full 100,000-product fixture with 100 connected conversations and five offered new questions per second, spanning search, comparisons, factual questions, and follow-ups. Measure cache-cold and representative-cache workloads separately.
20. **Honest performance accounting.** Publish offered rate, accepted rate, successful throughput, rejections, failures, expirations, queue delays, and end-to-end complete-answer p95. Rejections and expirations are not fast successful answers. Report the measured laptop operating point and whether the agreed target was achieved.
21. **Scope of verification.** Database failover and regional disaster scenarios are excluded. Real application/process recovery and interrupted cross-store ingestion remain required. No test, benchmark, model startup, or application behavior is claimed to have passed merely because this spec exists.

## Out of Scope

- Shopper accounts, login, cross-device identity, and account integrations.
- Checkout, payments, carts, order management, and write-capable commerce tools.
- Live shop integrations, live prices/stock, ongoing catalog updates, scheduled synchronization, product editing/removal, and variant-family management.
- Multilingual support and multiple currencies in v1.
- Administrator authentication, role-based permissions, and a raw-conversation inspection feature.
- Token-by-token answer streaming, elaborate shopper UI, and custom dashboard features already covered by the selected tools.
- Database failure/failover implementation or testing, full-cluster or regional disaster recovery, and a guarantee of uninterrupted inference.
- A transaction spanning PostgreSQL, Qdrant, inference, and cache operations.
- Exactly-once internal execution, unbounded retries, or a promise that every accepted question eventually receives an answer.
- Production capacity guarantees before measurement on the actual hardware.
- External public dataset or image services as required runtime dependencies.

## Further Notes

- The user accepted the v1 design and defaults at the end of the design interview. This document synthesizes those decisions; it does not reopen the product interview.
- The domain glossary supplies the canonical terms Shopper, Product, Catalog, Department, Category, Rating, Product dimensions, Product weight, Conversation, Shopper question, and Product answer.
- The architecture decisions require connection-independent durable questions, separate Qdrant storage, and a PostgreSQL work queue with recoverable processing.
- The verified development machine has an NVIDIA RTX 4060 Laptop GPU with approximately 8 GB VRAM and a running Linux Docker engine under WSL2. Free GPU memory varies, and inference startup, quality, and throughput still require validation.
- The initial model and resource settings are an implementation experiment within the accepted design. Record the selected revisions and measured operating point; report any quality or capacity shortfall before claiming the target is met.
- Similarity thresholds, session-rate limits, concrete deployment resource allocations, and other tuning values are configurable implementation details to validate. They must preserve the accepted constraints, finite deadlines, and global limits.
- This specification is published to the configured local Markdown issue tracker with ready-for-agent status. The testing boundaries are confirmed; additional triage is unnecessary.
- This is a multi-session build. Subsequent ticket decomposition should use independently verifiable increments and explicit blocking dependencies, starting from a running path through durable question acceptance and a saved answer.
