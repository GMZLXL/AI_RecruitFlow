from __future__ import annotations

from typing import Literal

from app.domain import Role

from .common import (
    EntityRead,
    Schema,
)


class UserRead(EntityRead):
    display_name: str
    role: Role
    department: str
    active: bool


class Identity(Schema):
    user: UserRead
    mode: Literal["mock"] = "mock"
    authentication: Literal["development_only"] = "development_only"
