ALTER TABLE conversations ADD COLUMN expired_at timestamptz;
CREATE INDEX conversations_retention ON conversations(created_at) WHERE expired_at IS NULL;
