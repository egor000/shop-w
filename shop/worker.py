import logging
import os
import time
from uuid import uuid4

from psycopg.types.json import Jsonb

from shop.inference import DeterministicProvider, InferenceProvider
from shop.store import connect, get_product

logger = logging.getLogger("shop.worker")


def process_one(provider: InferenceProvider) -> bool:
    with connect() as db:
        work = db.execute("SELECT question_id FROM work WHERE attempt_id IS NULL FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if work is None:
            return False
        question_id = work["question_id"]
        attempt_id = uuid4()
        db.execute("UPDATE work SET attempt_id = %s WHERE question_id = %s", (attempt_id, question_id))
        question = db.execute("UPDATE questions SET status = 'processing' WHERE id = %s RETURNING text", (question_id,)).fetchone()
        assert question is not None
    logger.info("processing question_id=%s attempt_id=%s", question_id, attempt_id)
    try:
        answer = provider.answer(question["text"], get_product("trail-cup"))
    except Exception:
        # Never log provider exception text: it may contain shopper content.
        with connect() as db:
            db.execute("UPDATE questions SET status = 'failed' WHERE id = %s", (question_id,))
            db.execute("DELETE FROM work WHERE question_id = %s", (question_id,))
        logger.warning("failed question_id=%s attempt_id=%s", question_id, attempt_id)
        return True
    with connect() as db:
        db.execute("UPDATE questions SET status = 'completed', answer = %s WHERE id = %s", (Jsonb(answer.model_dump()), question_id))
        db.execute("DELETE FROM work WHERE question_id = %s", (question_id,))
    logger.info("completed question_id=%s attempt_id=%s", question_id, attempt_id)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    provider = DeterministicProvider(float(os.environ.get("DETERMINISTIC_DELAY_SECONDS", "2")))
    while True:
        if not process_one(provider):
            time.sleep(0.2)


if __name__ == "__main__":
    main()
