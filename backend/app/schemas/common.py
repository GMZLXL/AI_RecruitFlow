from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Id = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
CustomFields = dict[Literal["organization.referral_tag"], Annotated[NonEmpty, Field(max_length=120)]]
T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Response(Schema, Generic[T]):
    data: T
    request_id: str


class Pagination(Schema):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class ListResponse(Response[list[T]], Generic[T]):
    pagination: Pagination


class ApiError(Schema):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(Schema):
    error: ApiError
    request_id: str


class EntityRead(Schema):
    id: str
    version: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DeleteResult(Schema):
    id: str
    version: int
    deleted_at: AwareDatetime


class DeleteRequest(Schema):
    change_reason: NonEmpty = Field(max_length=500)
