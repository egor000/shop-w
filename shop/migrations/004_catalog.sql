CREATE TABLE catalog_releases (
    id text PRIMARY KEY,
    product_count integer NOT NULL,
    embedding_model text NOT NULL,
    preprocessing text NOT NULL,
    status text NOT NULL CHECK (status IN ('loading', 'ready', 'failed')),
    ready_at timestamptz,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    error text
);
CREATE TABLE catalog_progress (
    release_id text NOT NULL REFERENCES catalog_releases(id),
    batch_start integer NOT NULL,
    batch_end integer NOT NULL,
    PRIMARY KEY (release_id, batch_start)
);
