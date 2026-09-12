CREATE TABLE inference_control (
    id boolean PRIMARY KEY DEFAULT TRUE CHECK (id),
    consecutive_failures integer NOT NULL DEFAULT 0,
    breaker_state text NOT NULL DEFAULT 'closed' CHECK (breaker_state IN ('closed', 'open', 'half_open')),
    opened_at timestamptz,
    probe_attempt_id uuid
);
INSERT INTO inference_control (id) VALUES (TRUE);
CREATE TABLE inference_leases (
    attempt_id uuid PRIMARY KEY,
    lease_expires_at timestamptz NOT NULL
);
