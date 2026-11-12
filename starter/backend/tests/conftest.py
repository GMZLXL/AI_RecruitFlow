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

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    engine.dispose()
    _tmp.cleanup()


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
