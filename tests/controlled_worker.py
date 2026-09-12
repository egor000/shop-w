"""Real worker entry point with only its inference boundary substituted."""
import os
import time

from shop.inference import TransientInferenceError
from shop.models import Product, ProductAnswer, ProductLink
from shop.worker import main


class ControlledProvider:
    def answer(self, question: str, product: Product, *, timeout_seconds: float) -> ProductAnswer:
        time.sleep(float(os.environ.get("TEST_INFERENCE_DELAY", "0.1")))
        mode = os.environ.get("TEST_INFERENCE_ERROR")
        if mode == "transient":
            raise TransientInferenceError("Unavailable: raw provider text must not be logged")
        if mode == "permanent":
            raise ValueError("Invalid provider response: raw text must not be logged")
        return ProductAnswer(text=os.environ.get("TEST_INFERENCE_RESULT", "Controlled answer"),
                             products=[ProductLink(name=product.name, url=f"/products/{product.id}")])


if __name__ == "__main__":
    main(ControlledProvider())
