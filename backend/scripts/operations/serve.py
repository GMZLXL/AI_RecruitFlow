"""Container entry point: explicit migration then one API process, no access URL logs."""

import os

from alembic.config import Config

from alembic import command
from app.core.config import BACKEND_ROOT
from app.core.logging import configure_logging
from app.core.runtime import validate_runtime


def main():
    configure_logging()
    validate_runtime()
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    os.execvp("python", ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
        "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"])


if __name__ == "__main__":
    main()
