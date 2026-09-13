"""Bounded read-only catalog conversations; model output never chooses product URLs."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shop.models import Product, ProductAnswer, ProductLink
from shop.store import catalog_ready, resolve_products, conversation_context, products_by_ids, product_search_release
from shop.vector_store import search as vector_search
from shop.question_context import classify_question

if TYPE_CHECKING:
    from shop.inference import VLLMProvider


class ProductDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    references: list[str] = Field(min_length=1, max_length=6)


class ProductConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    category: str | None = None
    department: str | None = None
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_length_cm: float | None = Field(default=None, ge=0)
    max_width_cm: float | None = Field(default=None, ge=0)
    max_height_cm: float | None = Field(default=None, ge=0)
    max_weight_kg: float | None = Field(default=None, ge=0)
    in_stock: bool | None = None
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

    def allows(self, product: Product) -> bool:
        return ((self.category is None or self.category.casefold() in (product.category.casefold(), product.category_id.casefold()))
                and (self.department is None or self.department.casefold() in (product.department.casefold(), product.department_id.casefold()))
                and (self.min_price_cents is None or product.price_cents >= self.min_price_cents)
                and (self.max_price_cents is None or product.price_cents <= self.max_price_cents)
                and (self.min_rating is None or (product.rating_average is not None and product.rating_count > 0 and product.rating_average >= self.min_rating))
                and (self.max_length_cm is None or product.length_cm <= self.max_length_cm)
                and (self.max_width_cm is None or product.width_cm <= self.max_width_cm)
                and (self.max_height_cm is None or product.height_cm <= self.max_height_cm)
                and (self.max_weight_kg is None or product.weight_kg <= self.max_weight_kg)
                and (self.in_stock is None or (product.stock > 0) == self.in_stock)
                and all(str(product.attributes.get(key)).casefold() == str(value).casefold() for key, value in self.attributes.items()))


class ProductSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=400)
    constraints: ProductConstraints = Field(default_factory=ProductConstraints)
    reset_constraints: bool = False


TOOLS = [{"type": "function", "function": {
    "name": "product_details", "description": "Look up exact product names or IDs for factual questions and comparisons. Short ambiguous names require clarification.",
    "parameters": ProductDetails.model_json_schema(),
}}, {"type": "function", "function": {
    "name": "search_products", "description": "Discover/refine products. Supply only changed constraints; omitted fields persist from the conversation. Null removes a specific constraint. Reset all constraints only when the shopper explicitly changes topic or removes previous requirements. Prices use USD cents, dimensions cm, weight kg.",
    "parameters": ProductSearch.model_json_schema(),
}}]


def product_links(products: list[Product]) -> list[ProductLink]:
    return [ProductLink(name=product.name, url=f"/products/{product.id}") for product in products]


def recorded_facts(products: list[Product]) -> str:
    attributes = sorted({key for product in products for key in product.attributes})
    lines = []
    for product in products:
        rating = f"{product.rating_average:g}/5 ({product.rating_count} ratings)" if product.rating_average is not None and product.rating_count else "unrated"
        lines.append(f"{product.name}: USD {product.price_cents / 100:.2f}; stock {product.stock}; rating {rating}; "
                     f"dimensions {product.length_cm:g} × {product.width_cm:g} × {product.height_cm:g} cm; weight {product.weight_kg:g} kg (product, excluding packaging).")
        lines.extend(f"{key}: {product.attributes.get(key, 'not recorded / not applicable')}" for key in attributes)
    return "\n".join(lines)


def answer_question(provider: VLLMProvider, question_id: UUID, question: str, *, timeout_seconds: float) -> ProductAnswer:
    deadline = time.monotonic() + timeout_seconds
    if not catalog_ready():
        return ProductAnswer(text="The catalog is not ready. Please try again later.", products=[])
    history, state = conversation_context(question_id)
    if not history and classify_question(question, has_prior_questions=False) == "history_dependent":
        return ProductAnswer(text="Which product do you mean? Please give its name or product link.", products=[])
    constraints = ProductConstraints.model_validate(state.get("constraints", {}))
    messages: list[dict[str, Any]] = [{"role": "system", "content":
        "You are a shopping assistant. Use read-only tools for product facts. Never invent product identity, attributes or values. "
        "Preserve the shopper's constraints unless explicitly changed. Compare compatible units and explain missing or inapplicable facts. "
        "Ask for clarification when identity is ambiguous. Return final JSON with text and products; catalog links and recorded facts are attached by the application. "
        "Conversation memory: " + json.dumps(state)}]
    for turn in history[-8:]:
        messages.extend([{"role": "user", "content": turn.text}, {"role": "assistant", "content": turn.answer.text if turn.answer else ""}])
    messages.append({"role": "user", "content": question})
    history_pairs = min(len(history), 8)
    products = products_by_ids(state.get("product_ids", []))
    interactions: list[dict[str, Any]] = []
    for index in range(3):
        while True:
            # vLLM 0.8.5 accepts tool definitions through template kwargs on
            # /tokenize; later releases also expose a top-level tools field.
            tokenized = provider.exchange("/tokenize", {
                "model": provider.model, "messages": messages, "add_generation_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False, "tools": TOOLS},
            }, timeout_seconds=deadline - time.monotonic())
            if int(tokenized["count"]) + 512 <= min(4096, int(tokenized["max_model_len"])):
                break
            if history_pairs:
                del messages[1:3]
                history_pairs -= 1
            else:
                return ProductAnswer(text="This question and its product evidence exceed the available context. Please narrow the question or comparison.", products=[], context_state={**state, "tool_interactions": interactions})
        body = provider.exchange("/v1/chat/completions", {
            "model": provider.model, "messages": messages, "tools": TOOLS,
            "tool_choice": "auto" if index < 2 else "none", "temperature": .7,
            "top_p": .8, "max_tokens": 512, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }, timeout_seconds=deadline - time.monotonic())
        message = body["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            content = str(message.get("content") or "").strip()
            if content.startswith("```"):
                content = content.split("```", 2)[1].removeprefix("json").strip()
            try:
                text = str(json.loads(content)["text"])
            except (ValueError, KeyError, TypeError):
                text = content
            if not products:
                return ProductAnswer(text=text or "Please specify which products you want to compare.", products=[])
            return ProductAnswer(text=text + "\n\nRecorded facts:\n" + recorded_facts(products), products=product_links(products),
                                 context_state={"constraints": constraints.model_dump(exclude_none=True), "product_ids": [p.id for p in products], "tool_interactions": interactions})
        if index == 2 or len(calls) > 2:
            return ProductAnswer(text="Please narrow the comparison to a few named products.", products=[])
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            try:
                name = call["function"]["name"]
                if name == "search_products":
                    search = ProductSearch.model_validate_json(call["function"]["arguments"])
                    previous = {} if search.reset_constraints else constraints.model_dump()
                    changed = search.constraints.model_dump(exclude_unset=True)
                    if "attributes" in changed:
                        changed["attributes"] = {**previous.get("attributes", {}), **changed["attributes"]}
                    constraints = ProductConstraints.model_validate({**previous, **changed})
                    release = product_search_release()
                    ids = vector_search(search.query, release, limit=100, score_threshold=0.0) if release else []
                    products = [p for p in products_by_ids(ids) if constraints.allows(p)][:6]
                    result: object = {"products": [p.model_dump() for p in products], "constraints": constraints.model_dump(exclude_none=True)}
                    interactions.append({"tool": name, "arguments": search.model_dump(), "result": result})
                    if not products:
                        return ProductAnswer(text="No matching products satisfy the recorded requirements. Would you like to change a constraint?", products=[],
                                             context_state={"constraints": constraints.model_dump(exclude_none=True), "product_ids": [], "tool_interactions": interactions})
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
                    continue
                if name != "product_details":
                    raise ValueError("Unknown catalog tool")
                args = ProductDetails.model_validate_json(call["function"]["arguments"])
                selected: list[Product] = []
                for reference in args.references:
                    matches = resolve_products(reference)
                    if len(matches) != 1:
                        text = (f"Which product do you mean by '{reference}'? Please use its full name or product ID."
                                if matches else f"No product matching '{reference}' is recorded. Please check the name.")
                        return ProductAnswer(text=text, products=product_links(matches), context_state={
                            "constraints": constraints.model_dump(exclude_none=True),
                            "product_ids": [p.id for p in products], "tool_interactions": interactions,
                        })
                    if matches[0].id not in {product.id for product in selected}:
                        selected.append(matches[0])
                products = selected
                result = [product.model_dump() for product in products]
                interactions.append({"tool": name, "arguments": args.model_dump(), "result": result})
            except (ValueError, ValidationError, KeyError, TypeError):
                result = {"error": "Invalid arguments. Use the documented read-only catalog tool schema."}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
    return ProductAnswer(text="Please narrow your question.", products=[])
