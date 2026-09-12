import time
from typing import Protocol

from shop.models import Product, ProductAnswer, ProductLink


class InferenceProvider(Protocol):
    def answer(self, question: str, product: Product) -> ProductAnswer: ...


class DeterministicProvider:
    def __init__(self, delay_seconds: float = 2) -> None:
        self.delay_seconds = delay_seconds

    def answer(self, question: str, product: Product) -> ProductAnswer:
        time.sleep(self.delay_seconds)
        return ProductAnswer(
            text=(f"{product.name}: {product.description} "
                  f"Price: USD {product.price_cents / 100:.2f}. "
                  f"Stock: {product.stock}. Rating: {product.rating_average}/5 ({product.rating_count} ratings). "
                  f"Dimensions: {product.length_cm:g} × {product.width_cm:g} × {product.height_cm:g} cm. "
                  f"Product weight: {product.weight_kg:g} kg. "
                  "This demo provides the recorded facts for this product only."),
            products=[ProductLink(name=product.name, url=f"/products/{product.id}")],
        )
