from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import current_user
from app.db import (
    User,
    get_db,
)

DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(current_user)]
Key = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=150)]
Version = Annotated[int, Header(alias="If-Match", ge=1)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def envelope(request: Request, data):
    return {"data": data, "request_id": request.state.request_id}


def listing(request: Request, db: Session, query, page: int, page_size: int, read):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        **envelope(request, [read(row) for row in rows]),
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }
