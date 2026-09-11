# Keep accepted questions and their work records in PostgreSQL

Use a PostgreSQL work queue with leases and attempt tokens instead of adding a separate message broker. Committing a shopper question and its work record together closes the acceptance-to-enqueue failure gap while keeping the initial deployment small; this transaction does not include Qdrant, inference, or cache writes. The trade-off is that the application must implement lease recovery, retry scheduling, duplicate suppression, and terminal-state fencing, and queue traffic shares capacity with other relational data.
