from datetime import datetime
from typing import Literal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

QuestionStatus = Literal["waiting", "processing", "completed", "failed", "expired", "cancelled"]


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: UUID
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must contain text")
        if "\x00" in value:
            raise ValueError("Question cannot contain null characters")
        return value


class ProductLink(BaseModel):
    name: str
    url: str


class ProductAnswer(BaseModel):
    text: str
    products: list[ProductLink]
    context_state: dict[str, Any] = Field(default_factory=dict, exclude=True)


class Question(BaseModel):
    id: UUID
    submission_id: UUID
    text: str
    status: QuestionStatus
    accepted_at: datetime
    deadline: datetime
    answer: ProductAnswer | None
    attempt_count: int
    recovery_count: int
    last_error: str | None
    terminal_at: datetime | None


class Attempt(BaseModel):
    id: UUID
    number: int
    worker_id: UUID
    started_at: datetime
    lease_expires_at: datetime
    finished_at: datetime | None
    outcome: str


class OperationalQuestion(BaseModel):
    id: UUID
    status: QuestionStatus
    accepted_at: datetime
    deadline: datetime
    attempt_count: int
    recovery_count: int
    last_error: str | None
    terminal_at: datetime | None
    next_attempt_at: datetime | None
    attempts: list[Attempt]


class Conversation(BaseModel):
    id: UUID
    questions: list[Question]


class Product(BaseModel):
    id: str
    name: str
    description: str
    department: str
    category: str
    price_cents: int
    stock: int
    rating_average: float | None
    rating_count: int
    length_cm: float
    width_cm: float
    height_cm: float
    weight_kg: float
    brand: str = ""
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)
    department_id: str = ""
    category_id: str = ""
    currency: str = "USD"
    measurement_configuration: str = "assembled product"
    image_url: str = "/static/product-placeholder.svg"
