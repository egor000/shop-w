import logging
import os
import time
import math
from datetime import datetime, timezone
from threading import Event, Thread
from uuid import UUID, uuid4
from typing import Literal

from shop.inference import DeterministicProvider, InferenceProvider, TransientInferenceError, VLLMProvider
from shop.store import catalog_ready, get_product, is_standalone_question, product_search_release
from shop.semantic_cache import lookup as cache_lookup, put as cache_put
from shop.tracing import configure, span
from shop.vector_store import search as vector_search
from shop import work_queue

logger = logging.getLogger("shop.worker")


def keep_lease(claim: work_queue.Claim, lease_seconds: float, stop: Event) -> None:
    while not stop.wait(lease_seconds / 3):
        try:
            if not work_queue.renew(claim, lease_seconds):
                return
        except Exception:
            logger.warning("renewal_unavailable question_id=%s attempt_id=%s", claim.question_id, claim.attempt_id)
            return


def process_one(provider: InferenceProvider, worker_id: UUID, lease_seconds: float) -> bool:
    claim = work_queue.claim(worker_id, lease_seconds)
    if claim is None:
        return False
    logger.info("processing question_id=%s attempt_id=%s attempt_number=%s", claim.question_id, claim.attempt_id, claim.number)
    stop = Event()
    heartbeat = Thread(target=keep_lease, args=(claim, lease_seconds, stop), daemon=True)
    heartbeat.start()
    failure: Literal["transient_inference", "permanent_inference"] | None = None
    try:
        # The legacy fixture product is opt-in for pre-catalog tests only. A
        # deployed catalog must never fabricate a product while it is absent
        # or not ready.
        product_id: str | None = (
            "trail-cup" if os.environ.get("LEGACY_DEMO_FALLBACK") == "true" else None
        )
        if catalog_ready():
            release = product_search_release()
            with span("vector.search", release=release or "", limit="1"):
                matches = vector_search(claim.text, release, limit=1) if release else []
            if matches:
                product_id = matches[0]
            else:
                product_id = None
        standalone = is_standalone_question(claim.question_id)
        answer = cache_lookup(claim.text, standalone=standalone)
        if answer is None:
            with span("llm.chat", provider=provider.__class__.__name__, model=os.environ.get("VLLM_MODEL", "Qwen/Qwen3-1.7B")):
                answer = provider.answer(claim.text, get_product(product_id) if product_id else None,
                                         timeout_seconds=max(0, (claim.deadline - datetime.now(timezone.utc)).total_seconds()))
            cache_put(claim.text, answer, standalone=standalone)
    except TransientInferenceError:
        answer = None
        failure = "transient_inference"
    except Exception:
        # Never log provider exception text: it may contain shopper content.
        answer = None
        failure = "permanent_inference"
    finally:
        stop.set()
        heartbeat.join()
    published = work_queue.finish(claim, answer, failure)
    logger.info("finished question_id=%s attempt_id=%s published=%s", claim.question_id, claim.attempt_id, published)
    return True


def main(provider: InferenceProvider | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    configure()
    if provider is None:
        if os.environ.get("INFERENCE_BACKEND") == "vllm":
            provider = VLLMProvider()
        else:
            provider = DeterministicProvider(float(os.environ.get("DETERMINISTIC_DELAY_SECONDS", "2")))
    lease_seconds = float(os.environ.get("WORKER_LEASE_SECONDS", "10"))
    if not math.isfinite(lease_seconds) or lease_seconds <= 0:
        raise ValueError("WORKER_LEASE_SECONDS must be positive and finite")
    worker_id = uuid4()
    while True:
        if not process_one(provider, worker_id, lease_seconds):
            time.sleep(0.2)


if __name__ == "__main__":
    main()
