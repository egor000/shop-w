ALTER TABLE questions ADD COLUMN IF NOT EXISTS context_state jsonb NOT NULL DEFAULT '{}';
