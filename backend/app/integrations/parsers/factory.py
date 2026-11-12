from .base import Parser
from .deepseek import DeepSeekParser
from .mock import MockParser


def get_parser() -> Parser:
    from app.services.ai_settings import connection

    settings = connection()
    provider = settings.provider
    if provider == "mock":
        return MockParser()
    if provider == "deepseek":
        return DeepSeekParser(connection=settings)
    raise RuntimeError("AI_PROVIDER must be mock or deepseek")
