"""Export implemented routes without starting a server or creating a database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["APP_ENV"] = "development"
os.environ["APP_MODE"] = "mock"

from app.main import app  # noqa: E402

path = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
document = app.openapi()
if args.check:
    if not path.exists() or yaml.safe_load(path.read_text(encoding="utf-8")) != document:
        raise SystemExit("OpenAPI contract drift. Run npm run contracts:generate.")
else:
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Exported {len(document['paths'])} implemented paths to {path.name}")
