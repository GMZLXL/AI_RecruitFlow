import os
import tempfile
from pathlib import Path

import pytest

_cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
_cache.mkdir(exist_ok=True)
_tmp = tempfile.TemporaryDirectory(prefix="mock-tests-", dir=_cache)
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_tmp.name) / "test.db")
os.environ["APP_MODE"] = "mock"
os.environ["APP_ENV"] = "development"

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from alembic import command  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield
    engine.dispose()
    _tmp.cleanup()


@pytest.fixture
def client():
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolated_parser_config(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
