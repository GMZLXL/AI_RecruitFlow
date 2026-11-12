import os

from .base import Parser
from .deepseek import DeepSeekParser
from .mock import MockParser


def get_parser() -> Parser:
    provider = os.getenv("AI_PROVIDER", "mock")
    if provider == "mock":
        return MockParser()
    if provider == "deepseek":
        return DeepSeekParser()
    raise RuntimeError("AI_PROVIDER must be mock or deepseek")
