"""Discover actual schemas in ignored local storage; does not read/write table records."""

import asyncio
import json

from app.core.config import PROJECT_ROOT
from app.integrations.smartsheet.base import SheetError
from app.integrations.smartsheet.discovery import discover_tools


async def main() -> int:
    try:
        tools = await discover_tools()
    except SheetError as exc:
        print(exc.code)
        return 2
    destination = PROJECT_ROOT / ".tools" / "tencent-mcp-tools.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(
        json.dumps({"verified_business_writes": False, "tools": tools}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Discovered {len(tools)} tool schemas in ignored local .tools; business writes remain blocked_by_schema"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
