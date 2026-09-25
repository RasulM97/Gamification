from dataclasses import dataclass
from typing import Literal

MAX_CONDITIONS = 20
MAX_FIELD_DEPTH = 5
MAX_RULES_PER_EVENT = 100
MAX_IN_VALUES = 50


@dataclass(frozen=True)
class Evaluation:
    status: Literal['MATCHED', 'NOT_MATCHED', 'INVALID']
    conditions_matched: int = 0
