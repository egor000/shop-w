ALTER TABLE questions DROP CONSTRAINT questions_status_check;
ALTER TABLE questions ADD CONSTRAINT questions_status_check
    CHECK (status IN ('waiting', 'processing', 'completed', 'failed', 'expired', 'cancelled'));
ALTER TABLE questions ADD COLUMN terminal_at timestamptz;
CREATE INDEX pending_question_deadlines ON questions(deadline)
    WHERE status IN ('waiting', 'processing');
-- Preserve known completion times; legacy results without attempt history stay unknown.
UPDATE questions q SET terminal_at = (
    SELECT max(finished_at) FROM attempts a WHERE a.question_id = q.id
) WHERE q.status IN ('completed', 'failed', 'expired');
