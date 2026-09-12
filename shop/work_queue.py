"""Durable work ownership. Each operation commits before returning to inference."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import uniform
from typing import Literal
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from shop.models import ProductAnswer
from shop.store import connect


@dataclass(frozen=True)
class Claim:
    question_id: UUID
    attempt_id: UUID
    text: str
    deadline: datetime
    number: int


def claim(worker_id: UUID, lease_seconds: float) -> Claim | None:
    with connect() as db:
        work = db.execute("""
            SELECT w.* FROM work w JOIN questions q ON q.id = w.question_id
            WHERE w.available_at <= clock_timestamp()
              AND (w.attempt_id IS NULL OR w.lease_expires_at <= clock_timestamp())
            ORDER BY q.accepted_at, q.id FOR UPDATE OF w SKIP LOCKED LIMIT 1
        """).fetchone()
        if work is None:
            return None
        question_id = work["question_id"]
        question = db.execute("SELECT * FROM questions WHERE id = %s FOR UPDATE", (question_id,)).fetchone()
        assert question is not None
        clock = db.execute("SELECT clock_timestamp() AS now").fetchone()
        assert clock is not None
        now = clock["now"]
        if work["attempt_id"] is not None:
            db.execute("UPDATE attempts SET outcome = 'abandoned', finished_at = clock_timestamp() WHERE id = %s", (work["attempt_id"],))
            db.execute("UPDATE questions SET recovery_count = recovery_count + 1 WHERE id = %s", (question_id,))
        if question["deadline"] <= now or question["attempt_count"] >= 3:
            status = "expired" if question["deadline"] <= now else "failed"
            error = "deadline_exceeded" if status == "expired" else "attempts_exhausted"
            db.execute("UPDATE questions SET status = %s, last_error = %s, terminal_at = clock_timestamp() WHERE id = %s", (status, error, question_id))
            db.execute("DELETE FROM work WHERE question_id = %s", (question_id,))
            return None
        question = db.execute("""
            UPDATE questions SET status = 'processing', attempt_count = attempt_count + 1
            WHERE id = %s RETURNING *
        """, (question_id,)).fetchone()
        assert question is not None
        attempt_id = uuid4()
        db.execute("""
            UPDATE work SET attempt_id = %s,
              lease_expires_at = LEAST(%s, clock_timestamp() + %s * interval '1 second')
            WHERE question_id = %s
        """, (attempt_id, question["deadline"], lease_seconds, question_id))
        db.execute("""
            INSERT INTO attempts (id, question_id, number, worker_id, lease_expires_at)
            SELECT %s, question_id, %s, %s, lease_expires_at FROM work WHERE question_id = %s
        """, (attempt_id, question["attempt_count"], worker_id, question_id))
        return Claim(question_id, attempt_id, question["text"], question["deadline"], question["attempt_count"])


def finish(claim: Claim, answer: ProductAnswer | None,
           failure: Literal["transient_inference", "permanent_inference"] | None = None) -> bool:
    with connect() as db:
        work = db.execute("SELECT * FROM work WHERE question_id = %s FOR UPDATE", (claim.question_id,)).fetchone()
        if work is None or work["attempt_id"] != claim.attempt_id:
            return False
        question = db.execute("SELECT * FROM questions WHERE id = %s FOR UPDATE", (claim.question_id,)).fetchone()
        clock = db.execute("SELECT clock_timestamp() AS now").fetchone()
        assert question is not None and clock is not None
        now = clock["now"]
        if question["status"] != "processing" or work["lease_expires_at"] <= now or claim.deadline <= now:
            return False
        if failure == "transient_inference" and claim.number < 3:
            available_at = min(claim.deadline, now + timedelta(seconds=uniform(.5, 1) * 2 ** (claim.number - 1)))
            db.execute("UPDATE work SET attempt_id = NULL, lease_expires_at = NULL, available_at = %s WHERE question_id = %s", (available_at, claim.question_id))
            db.execute("UPDATE questions SET status = 'waiting', last_error = %s WHERE id = %s", (failure, claim.question_id))
            db.execute("UPDATE attempts SET outcome = 'transient_failure', finished_at = %s WHERE id = %s", (now, claim.attempt_id))
            return True
        status = "completed" if answer else "failed"
        error = "attempts_exhausted" if failure == "transient_inference" else failure
        db.execute("UPDATE questions SET status = %s, answer = %s, last_error = %s, terminal_at = clock_timestamp() WHERE id = %s", (status, Jsonb(answer.model_dump()) if answer else None, error, claim.question_id))
        db.execute("UPDATE attempts SET outcome = %s, finished_at = clock_timestamp() WHERE id = %s", (status, claim.attempt_id))
        db.execute("DELETE FROM work WHERE question_id = %s", (claim.question_id,))
    return True


def renew(claim: Claim, lease_seconds: float) -> bool:
    with connect() as db:
        work = db.execute("SELECT * FROM work WHERE question_id = %s FOR UPDATE", (claim.question_id,)).fetchone()
        clock = db.execute("SELECT clock_timestamp() AS now").fetchone()
        assert clock is not None
        if (work is None or work["attempt_id"] != claim.attempt_id
                or work["lease_expires_at"] <= clock["now"] or claim.deadline <= clock["now"]):
            return False
        renewed = db.execute("""
            UPDATE work SET lease_expires_at = LEAST(%s, clock_timestamp() + %s * interval '1 second')
            WHERE question_id = %s AND attempt_id = %s
            RETURNING lease_expires_at
        """, (claim.deadline, lease_seconds, claim.question_id, claim.attempt_id)).fetchone()
        if renewed is None:
            return False
        db.execute("UPDATE attempts SET lease_expires_at = %s WHERE id = %s", (renewed["lease_expires_at"], claim.attempt_id))
        return True


def cancel(question_id: UUID) -> None:
    """Caller authorizes the immutable conversation association before entering."""
    with connect() as db:
        db.execute("SELECT question_id FROM work WHERE question_id = %s FOR UPDATE", (question_id,))
        db.execute("SELECT id FROM questions WHERE id = %s FOR UPDATE", (question_id,))
        terminal = db.execute("""
            WITH observed AS MATERIALIZED (SELECT clock_timestamp() AS now)
            UPDATE questions SET
              status = CASE WHEN deadline <= observed.now THEN 'expired' ELSE 'cancelled' END,
              last_error = CASE WHEN deadline <= observed.now THEN 'deadline_exceeded' ELSE NULL END,
              terminal_at = observed.now
            FROM observed WHERE id = %s AND status IN ('waiting', 'processing') RETURNING status, terminal_at
        """, (question_id,)).fetchone()
        if terminal is None:
            return
        db.execute("""
            UPDATE attempts SET outcome = %s, finished_at = %s
            WHERE id = (SELECT attempt_id FROM work WHERE question_id = %s)
        """, (terminal["status"], terminal["terminal_at"], question_id))
        db.execute("DELETE FROM work WHERE question_id = %s", (question_id,))


def expire() -> int:
    """Expire one bounded batch independently of inference availability."""
    with connect() as db:
        rows = db.execute("""
            SELECT w.question_id FROM work w JOIN questions q ON q.id = w.question_id
            WHERE q.deadline <= clock_timestamp() AND q.status IN ('waiting', 'processing')
            ORDER BY q.deadline FOR UPDATE OF w SKIP LOCKED LIMIT 100
        """).fetchall()
        for row in rows:
            question_id = row["question_id"]
            db.execute("SELECT id FROM questions WHERE id = %s FOR UPDATE", (question_id,))
            terminal = db.execute("""
                UPDATE questions SET status = 'expired', last_error = 'deadline_exceeded',
                  terminal_at = clock_timestamp()
                WHERE id = %s AND status IN ('waiting', 'processing') AND deadline <= clock_timestamp()
                RETURNING terminal_at
            """, (question_id,)).fetchone()
            if terminal is not None:
                db.execute("""
                    UPDATE attempts SET outcome = 'expired', finished_at = %s
                    WHERE id = (SELECT attempt_id FROM work WHERE question_id = %s)
                """, (terminal["terminal_at"], question_id))
                db.execute("DELETE FROM work WHERE question_id = %s", (question_id,))
        return len(rows)
