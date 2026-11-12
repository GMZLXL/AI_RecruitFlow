import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
if os.getenv("APP_ENV", "development") == "development":
    load_dotenv(BACKEND_ROOT / ".env")

# Docker/secret-store file references are read only by the server, never the web build.
for _name in ("DATABASE_URL", "DEEPSEEK_API_KEY", "TENCENT_DOCS_TOKEN", "WECOM_SECRET",
              "WECOM_CALLBACK_TOKEN", "WECOM_ENCODING_AES_KEY", "SESSION_CSRF_SECRET", "APP_SECRET_KEY"):
    _file = os.getenv(_name + "_FILE")
    if _file:
        if os.getenv(_name):
            raise RuntimeError(f"Conflicting environment/file secret source: {_name}")
        try:
            _path = Path(_file)
            if _path.stat().st_size > 65536:
                raise ValueError()
            os.environ[_name] = _path.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            raise RuntimeError(f"Cannot load server secret: {_name}") from None
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./recruitflow.db")
