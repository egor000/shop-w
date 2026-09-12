import time
from typing import Protocol

from shop.models import Product, ProductAnswer, ProductLink


class TransientInferenceError(Exception):
    """An unavailable or timed-out provider may be retried within the durable budget."""


class InferenceProvider(Protocol):
    def answer(self, question: str, product: Product | None, *, timeout_seconds: float) -> ProductAnswer: ...


class DeterministicProvider:
    def __init__(self, delay_seconds: float = 2) -> None:
        self.delay_seconds = delay_seconds

    def answer(self, question: str, product: Product | None, *, timeout_seconds: float) -> ProductAnswer:
        time.sleep(max(0, min(self.delay_seconds, timeout_seconds)))
        if self.delay_seconds >= timeout_seconds:
            raise TransientInferenceError("Inference deadline reached")
        if product is None:
            return ProductAnswer(text="I could not find a matching product in the ready catalog. Try a different product description.", products=[])
        return ProductAnswer(
            text=(f"{product.name}: {product.description} "
                  f"Price: USD {product.price_cents / 100:.2f}. "
                  f"Stock: {product.stock}. Rating: {product.rating_average}/5 ({product.rating_count} ratings). "
                  f"Dimensions: {product.length_cm:g} × {product.width_cm:g} × {product.height_cm:g} cm. "
                  f"Product weight: {product.weight_kg:g} kg. "
                  "This demo provides the recorded facts for this product only."),
            products=[ProductLink(name=product.name, url=f"/products/{product.id}")],
        )
