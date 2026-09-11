# Separate vector storage with Qdrant

Use Qdrant for vector storage rather than consolidating all storage into PostgreSQL with pgvector. The user explicitly chose separate persistence boundaries and rejected an architecture that assumes one transaction across all data models. Consequently, ingestion and cache writes must tolerate partial progress and retries; durable request acceptance and completed answers cannot depend on an atomic commit spanning Qdrant and the request-state store.
