ALTER TABLE questions ADD COLUMN attempt_count integer NOT NULL DEFAULT 0;
ALTER TABLE questions ADD COLUMN recovery_count integer NOT NULL DEFAULT 0;
ALTER TABLE questions ADD COLUMN last_error text;
ALTER TABLE questions DROP CONSTRAINT questions_status_check;
ALTER TABLE questions ADD CONSTRAINT questions_status_check
    CHECK (status IN ('waiting', 'processing', 'completed', 'failed', 'expired'));
ALTER TABLE work ADD COLUMN lease_expires_at timestamptz;
ALTER TABLE work ADD COLUMN available_at timestamptz NOT NULL DEFAULT clock_timestamp();
CREATE INDEX work_available ON work(available_at);
CREATE TABLE attempts (
    id uuid PRIMARY KEY,
    question_id uuid NOT NULL REFERENCES questions(id),
    number integer NOT NULL,
    worker_id uuid NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_expires_at timestamptz NOT NULL,
    finished_at timestamptz,
    outcome text NOT NULL DEFAULT 'processing',
    UNIQUE (question_id, number)
);
-- V1 claims have no recoverable owner identity; let new workers reclaim them.
UPDATE work SET attempt_id = NULL;
