from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class Question(BaseModel):
    id: UUID
    submission_id: UUID
    text: str
    status: Literal["waiting", "processing", "completed", "failed"]
    accepted_at: datetime
    deadline: datetime
    answer: ProductAnswer | None


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
    rating_average: float
    rating_count: int
    length_cm: float
    width_cm: float
    height_cm: float
    weight_kg: float
