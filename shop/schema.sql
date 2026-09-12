CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE conversations (
    id uuid PRIMARY KEY,
    session_hash text NOT NULL REFERENCES sessions(token_hash),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX conversations_session ON conversations(session_hash);
CREATE TABLE questions (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    submission_id uuid NOT NULL,
    text text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
    status text NOT NULL CHECK (status IN ('waiting', 'processing', 'completed', 'failed')),
    accepted_at timestamptz NOT NULL,
    deadline timestamptz NOT NULL,
    answer jsonb,
    UNIQUE (conversation_id, submission_id),
    CHECK ((status = 'completed') = (answer IS NOT NULL))
);
CREATE TABLE work (
    question_id uuid PRIMARY KEY REFERENCES questions(id),
    attempt_id uuid
);
CREATE TABLE products (
    id text PRIMARY KEY,
    facts jsonb NOT NULL
);
INSERT INTO products VALUES ('trail-cup', '{"id":"trail-cup","name":"Trail Cup","description":"A fictional reusable stainless-steel cup for everyday outings. Capacity: 450 ml.","department":"Outdoors","category":"Drinkware","price_cents":2499,"stock":35,"rating_average":4.6,"rating_count":28,"length_cm":8.5,"width_cm":8.5,"height_cm":12,"weight_kg":0.25}');
