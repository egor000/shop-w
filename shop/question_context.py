"""Conservative request classification shared by orchestration and cache reuse."""
import re
from typing import Literal


def classify_question(text: str, *, has_prior_questions: bool) -> Literal["standalone", "history_dependent"]:
    if has_prior_questions or re.search(
        r"\b(it|its|them|their|those|these|same|earlier|previous|above|instead|cheaper|lighter|smaller)\b|\b(that|this) (one|product)\b",
        text, re.IGNORECASE,
    ):
        return "history_dependent"
    return "standalone"
