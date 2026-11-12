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
os.environ["SYNC_WORKER_ENABLED"] = "false"
os.environ["WECOM_WORKER_ENABLED"] = "false"
os.environ["AUTH_MODE"] = "dev"

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
    import base64

    monkeypatch.setenv("APP_SECRET_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.delenv("DEV_PROXY_NETWORKS", raising=False)
    monkeypatch.setenv("WECOM_PROVIDER", "mock")
    monkeypatch.setenv("WECOM_CALLBACK_ENABLED", "false")
    monkeypatch.setenv("WECOM_SEND_ENABLED", "false")
    for key in ("WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_CALLBACK_TOKEN", "WECOM_ENCODING_AES_KEY", "WECOM_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("SMARTSHEET_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_SHEET_FAILURE", "none")
    monkeypatch.delenv("TENCENT_DOCS_TOKEN", raising=False)
