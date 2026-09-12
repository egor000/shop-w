"""Durable global inference slots and circuit-breaker coordination."""
from datetime import datetime, timedelta
from uuid import UUID

from typing import Any
from psycopg import Connection


SLOT_LIMIT = 2
FAILURE_THRESHOLD = 5
OPEN_SECONDS = 15


def try_acquire(db: Connection[Any], attempt_id: UUID, lease_expires_at: datetime, *, limit: int = SLOT_LIMIT) -> bool:
    """Acquire one shared slot, allowing at most one recovery probe."""
    db.execute("INSERT INTO inference_control (id) VALUES (TRUE) ON CONFLICT DO NOTHING")
    db.execute("DELETE FROM inference_leases WHERE lease_expires_at <= clock_timestamp()")
    row = db.execute("SELECT * FROM inference_control WHERE id = TRUE FOR UPDATE").fetchone()
    assert row is not None
    if row["breaker_state"] == "half_open" and row["probe_attempt_id"] is not None:
        probe = db.execute("SELECT 1 FROM inference_leases WHERE attempt_id = %s", (row["probe_attempt_id"],)).fetchone()
        if probe is None:
            db.execute("UPDATE inference_control SET breaker_state = 'open', opened_at = clock_timestamp(), probe_attempt_id = NULL WHERE id = TRUE")
            row["breaker_state"] = "open"
            row["probe_attempt_id"] = None
    active_row = db.execute("SELECT count(*) AS count FROM inference_leases").fetchone()
    assert active_row is not None
    active = active_row["count"]
    if active >= limit:
        return False
    now_row = db.execute("SELECT clock_timestamp() AS now").fetchone()
    assert now_row is not None
    now = now_row["now"]
    state = row["breaker_state"]
    if state == "open":
        if row["opened_at"] is None or row["opened_at"] > now - timedelta(seconds=OPEN_SECONDS):
            return False
        if row["probe_attempt_id"] is not None:
            return False
        db.execute("UPDATE inference_control SET breaker_state = 'half_open', probe_attempt_id = %s WHERE id = TRUE", (attempt_id,))
    elif state == "half_open":
        return False
    db.execute("INSERT INTO inference_leases (attempt_id, lease_expires_at) VALUES (%s, %s)", (attempt_id, lease_expires_at))
    return True


def renew(db: Connection[Any], attempt_id: UUID, lease_expires_at: datetime) -> None:
    db.execute("UPDATE inference_leases SET lease_expires_at = %s WHERE attempt_id = %s", (lease_expires_at, attempt_id))


def release(db: Connection[Any], attempt_id: UUID, *, transient_failure: bool = False) -> None:
    db.execute("DELETE FROM inference_leases WHERE attempt_id = %s", (attempt_id,))
    row = db.execute("SELECT * FROM inference_control WHERE id = TRUE FOR UPDATE").fetchone()
    if row is None:
        return
    if transient_failure:
        failures = row["consecutive_failures"] + 1
        if row["breaker_state"] == "half_open" or failures >= FAILURE_THRESHOLD:
            db.execute("UPDATE inference_control SET breaker_state = 'open', opened_at = clock_timestamp(), probe_attempt_id = NULL, consecutive_failures = %s WHERE id = TRUE", (failures,))
        else:
            db.execute("UPDATE inference_control SET consecutive_failures = %s WHERE id = TRUE", (failures,))
    else:
        db.execute("UPDATE inference_control SET breaker_state = 'closed', opened_at = NULL, probe_attempt_id = NULL, consecutive_failures = 0 WHERE id = TRUE")
