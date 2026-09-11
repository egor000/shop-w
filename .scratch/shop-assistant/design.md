# Shop assistant design

Status: Design interview complete. The user accepted the v1 implementation baseline on 2026-09-11 by confirming Q27 and subsequently confirmed the testing boundaries. The specification is published as ready-for-agent. No application implementation has started.

## Authoritative design

- [Published specification](spec.md): user stories, implementation and testing decisions, and scope for ticket decomposition and implementation.
- [Accepted v1 design](v1-review.md): scope, components, request lifecycle, overload policy, ingestion/cache contracts, operator experience, and acceptance evidence.
- [Synthetic catalog](catalog-design.md): the accepted hierarchy, fields, generation rules, and filtering semantics.
- [Domain glossary](../../CONTEXT.md): canonical product and conversation terminology.
- [Architecture decisions](../../docs/adr/): connection-independent question processing, separate Qdrant storage, and the PostgreSQL work queue.

The accepted design supersedes earlier research proposals, including PostgreSQL/pgvector consolidation, database failover requirements, external-only inference, administrator authentication, and token-by-token answer streaming. Model settings remain initial candidates to validate; the load and latency targets have not been demonstrated.

## Supporting research

- [Catalog candidates](catalog-research.md)
- [Storage alternatives](storage-research.md)
- [Local model candidates](model-research.md)

These notes retain investigated alternatives and uncertainties. They do not override the accepted design.

## Local runtime facts

Read-only inspection on 2026-09-11 found an NVIDIA RTX 4060 Laptop GPU with 8188 MiB VRAM (5780 MiB free at the latest check), a workspace Python 3.13.12 environment, and Docker Engine 28.5.1 running Linux under WSL2 through Docker Desktop 4.49.0. GPU visibility inside an inference container and model throughput have not been tested.

## Repository setup

Setup is complete. Root `AGENTS.md` points to the local Markdown tracker, default triage labels, and single-context domain rules in `docs/agents/`.
