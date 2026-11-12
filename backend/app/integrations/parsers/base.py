from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from app.schemas.ai import Extraction


@dataclass(frozen=True)
class ParseOutcome:
    extraction: Extraction = field(default_factory=lambda: Extraction(intent="unknown", should_confirm=True))
    provider: Literal["mock", "deepseek"] = "mock"
    error_code: str | None = None
    attempts: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None


class Parser(Protocol):
    async def parse(self, text: str, reference_time: datetime, timezone: str) -> ParseOutcome: ...
