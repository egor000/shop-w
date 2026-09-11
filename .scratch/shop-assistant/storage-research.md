# Storage options for the shop assistant

Research date: 2026-09-11. Status: proposal for the design interview, not an accepted architecture or a capacity guarantee.

## Recommendation

Start by proposing self-hosted PostgreSQL with pgvector for durable conversation/request state, a leased work queue, catalog facts and embeddings, and a separate semantic-cache table. Kubernetes production would use three PostgreSQL instances on different worker nodes under CloudNativePG; Compose development can use one instance with persistent storage. This reduces independently operated storage systems and permits request acceptance plus enqueueing in one transaction. It also concentrates retrieval, queue and cache load on the same database. This is an architectural inference, subject to benchmarking and failure testing.

The design targets of 100,000 products, five new questions per second and 100 concurrent conversations do not prove either option meets the ten-second answer target. Measure mixed workloads with the actual embedding dimensions, filters, cache growth, retention and inference hardware. Five requests per second sustained for thirty days is 12.96 million requests; peak traffic should not silently become the storage-sizing assumption.

| Option | Reason to choose | Added responsibility |
| --- | --- | --- |
| PostgreSQL + pgvector | One transactional durability system; facts and vectors can be queried together | Isolate queue latency from expensive retrieval, maintain indexes and vacuuming, benchmark filtered recall |
| PostgreSQL + Qdrant | Independent vector capacity and operational isolation; purpose-built distributed vector retrieval | Operate two replicated systems, coordinate ingestion/publication and backup/recovery, maintain consistency of vector references with catalog truth |

These tradeoffs are design judgments. Neither option needs Redis or a separate message broker solely to satisfy the present requirements.

## Durable acceptance and queue semantics

PostgreSQL documents `FOR UPDATE SKIP LOCKED` as useful for queue consumers, but it yields an inconsistent view and only skips row locks, not table locks. It does not by itself supply recovery, fairness or exactly-once processing. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE)

Proposed application contract: insert the request and runnable work atomically; acknowledge acceptance only after commit confirmation. Claim work in a short transaction, record a lease plus attempt token, then release the transaction before calling inference. Reclaim expired leases and fence final writes using the token and current request state. Persist one authoritative terminal result; execution may repeat. A dropped commit response means an uncertain outcome, so the browser retries the same stable identifier and the API reconciles it. Expired or cancelled requests cannot be completed by an old worker. A durable queue is the database records, not a notification mechanism.

With synchronous standbys configured, `synchronous_commit=on` waits for WAL durability on the required standbys. `remote_write` does not protect against a standby OS crash; `remote_apply` additionally waits for replay and visibility. With no synchronous standby configuration, `on` provides only local durability. Keep `fsync` enabled. [PostgreSQL WAL settings](https://www.postgresql.org/docs/current/runtime-config-wal.html#GUC-SYNCHRONOUS-COMMIT)

CloudNativePG disables synchronous replication by default. Proposed production policy: three instances, synchronous `method: any`, `number: 1`, `dataDurability: required`. Required durability pauses commits when the required standby cannot participate; `preferred` can weaken the protection to continue writes. Replicas and their storage must span the promised worker-node failure boundary. [CloudNativePG 1.29 replication](https://cloudnative-pg.io/docs/1.29/replication/)

Synchronous commit alone does not prove that every possible failover promotes a replica containing acknowledged writes. CloudNativePG documents `failoverQuorum: true` to refuse promotion when it cannot establish that property; its 1.29 documentation still describes the feature as experimental. Evaluate and pin an operator version, retain isolation/fencing behavior, and test failover before accepting the guarantee. Unsafe forced promotion can invalidate it. [CloudNativePG 1.29 failover](https://cloudnative-pg.io/docs/1.29/failover/)

The zero-loss promise should cover acknowledged requests during a single worker-node loss, with functioning remaining storage/control plane and the specified replication/promotion policy. It does not cover correlated loss of all durable copies. Do not acknowledge new requests while the durability requirement cannot be met. Failover can interrupt connections and pause acceptance; establish a recovery-time target rather than promise uninterrupted database writes. Static catalog reads may use healthy, validated replicas to continue retrieval during primary recovery. Backups and restore drills remain separate from replication.

## pgvector search and semantic cache

pgvector defaults to exact search. HNSW and IVFFlat trade recall for speed; HNSW generally has the better speed/recall tradeoff but costs more memory and build time. Approximate-index filters are applied after the index scan and can produce too few matches. Iterative scans, available since 0.8.0, search farther up to configured limits. Ordinary indexes with exact search, partial indexes or partitioning can help selective filters. Compare approximate results against exact results for representative category, price and attribute filters. [Official pgvector documentation](https://github.com/pgvector/pgvector#filtering)

Proposed cache policy: separate cache vectors from product vectors; key eligibility by immutable catalog release, embedding/model/prompt version, locale and structured constraints. Restrict reuse to standalone public questions. Validate cached product references and present price/availability from catalog facts. Similarity alone cannot establish that two requests have equivalent constraints. Cache writes are expendable; accepted request records are not. Bound cache size and expiry independently of conversation retention.

## What a separate Qdrant would require

Qdrant recommends three or more nodes and replication factor at least two for HA. Replica placement must reflect independent failure domains; self-hosted deployments do not automatically provide zone-aware placement. Permanent node replacement and consensus cleanup require operator action in self-hosted Qdrant. [Qdrant resilience](https://qdrant.tech/documentation/scaling/resilience/)

Collection metadata uses Raft; point writes do not receive atomic distributed-transaction guarantees from that consensus. [Qdrant horizontal scaling](https://qdrant.tech/documentation/scaling/horizontal-scaling/)

`write_consistency_factor` controls required write acknowledgments and defaults to one. Read consistency and write ordering are separate controls. Failed writes may have partially applied and need retry. For an immutable v1 catalog, a candidate is three nodes, replication factor two, write consistency two during loading, then publication only after successful validation on replicas. This allows a surviving replica to serve reads after one node fails, while ingestion/cache writes requiring both copies may stop. Replication factor three with write consistency two offers different availability and storage costs. These are proposals to test, not unconditional guarantees. [Qdrant consistency guarantees](https://qdrant.tech/documentation/scaling/consistency-guarantees/)

Keep durable chat state and request acceptance in PostgreSQL even if Qdrant is selected. Use deterministic product IDs and resumable ingestion. Semantic-cache insertion failures should become cache misses, without losing the shopper's answer or request.

## Decision still needed

Confirm whether a consolidated PostgreSQL + pgvector deployment fits the user's preference for a self-hosted vector store, and define the allowable recovery pause after losing the primary node. Choose a separate Qdrant only for an explicit preference or measured retrieval/isolation requirement.
