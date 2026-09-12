import json
import os
import time
from typing import Any, Protocol
from urllib import request

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


class VLLMProvider:
    """OpenAI-compatible local vLLM provider with a bounded grounded prompt."""
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("VLLM_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.model = model or os.environ.get("VLLM_MODEL", "Qwen/Qwen3-1.7B")

    def answer(self, question: str, product: Product | None, *, timeout_seconds: float) -> ProductAnswer:
        if timeout_seconds <= 0:
            raise TransientInferenceError("Inference deadline reached")
        evidence = "No matching catalog evidence is available."
        if product is not None:
            evidence = json.dumps(product.model_dump(), sort_keys=True)
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": "Answer only from the supplied catalog evidence. Return JSON with text and products (name,url). If evidence is absent, explain the limitation and return no products."},
            {"role": "user", "content": f"Question: {question}\nCatalog evidence: {evidence}"},
        ], "temperature": 0, "max_tokens": 512, "stream": False}
        try:
            data: Any = json.dumps(payload).encode()
            req = request.Request(self.base_url + "/v1/chat/completions", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
            with request.urlopen(req, timeout=min(timeout_seconds, 30)) as response:
                body: Any = json.loads(response.read())
            content = body["choices"][0]["message"]["content"]
            if "```" in content:
                content = content.split("```", 2)[1]
                content = content.removeprefix("json").strip()
            parsed: Any = json.loads(content)
            return ProductAnswer.model_validate(parsed)
        except TimeoutError as error:
            raise TransientInferenceError("Inference deadline reached") from error
        except Exception as error:
            raise TransientInferenceError("vLLM unavailable or invalid response") from error
