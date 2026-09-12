"""Own the relational transactions; no inference call runs inside one."""
import hashlib
import os
import secrets
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from shop.models import Conversation, Product, Question, Submission


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def connect() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=5)


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_session(token: str | None) -> str:
    with connect() as db:
        if token and db.execute("SELECT 1 FROM sessions WHERE token_hash = %s", (session_hash(token),)).fetchone():
            return token
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions (token_hash) VALUES (%s)", (session_hash(token),))
        return token


def create_conversation(token: str) -> UUID:
    conversation_id = uuid4()
    with connect() as db:
        if not db.execute("SELECT 1 FROM sessions WHERE token_hash = %s", (session_hash(token),)).fetchone():
            raise NotFound
        db.execute("INSERT INTO conversations (id, session_hash) VALUES (%s, %s)", (conversation_id, session_hash(token)))
    return conversation_id


def get_conversation(conversation_id: UUID, token: str) -> Conversation:
    with connect() as db:
        if not db.execute("SELECT 1 FROM conversations WHERE id = %s AND session_hash = %s", (conversation_id, session_hash(token))).fetchone():
            raise NotFound
        rows = db.execute("SELECT * FROM questions WHERE conversation_id = %s ORDER BY accepted_at, id", (conversation_id,)).fetchall()
        return Conversation(id=conversation_id, questions=[Question.model_validate(row) for row in rows])


def submit(conversation_id: UUID, token: str, submission: Submission) -> Question:
    with connect() as db:
        if not db.execute("SELECT 1 FROM conversations WHERE id = %s AND session_hash = %s FOR UPDATE", (conversation_id, session_hash(token))).fetchone():
            raise NotFound
        existing = db.execute("SELECT * FROM questions WHERE conversation_id = %s AND submission_id = %s", (conversation_id, submission.submission_id)).fetchone()
        if existing:
            if existing["text"] != submission.text:
                raise Conflict("Submission ID already used for different content")
            return Question.model_validate(existing)
        if db.execute("SELECT 1 FROM questions WHERE conversation_id = %s AND status IN ('waiting', 'processing')", (conversation_id,)).fetchone():
            raise Conflict("A question is already pending in this conversation")
        row = db.execute("""
            INSERT INTO questions (id, conversation_id, submission_id, text, status, accepted_at, deadline)
            VALUES (%s, %s, %s, %s, 'waiting', statement_timestamp(), statement_timestamp() + interval '2 minutes')
            RETURNING *
        """, (uuid4(), conversation_id, submission.submission_id, submission.text)).fetchone()
        assert row is not None
        db.execute("INSERT INTO work (question_id) VALUES (%s)", (row["id"],))
        question = Question.model_validate(row)
    return question


def get_product(product_id: str) -> Product:
    with connect() as db:
        row = db.execute("SELECT facts FROM products WHERE id = %s", (product_id,)).fetchone()
        if row is None:
            raise NotFound
        return Product.model_validate(row["facts"])
