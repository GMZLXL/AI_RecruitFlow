from typing import Literal

from pydantic import Field, SecretStr, model_validator

from .common import NonEmpty, Schema


class AISettingsRead(Schema):
    version: int
    provider: Literal["mock", "deepseek"]
    model: str
    has_api_key: bool
    key_source: Literal["managed", "environment", "none"]
    secret_store_ready: bool
    real_calls_allowed: bool
    status: Literal["mock_only", "blocked_by_credentials", "configured_not_verified", "mode_mismatch"]


class AISettingsUpdate(Schema):
    provider: Literal["mock", "deepseek"]
    model: NonEmpty = Field(max_length=120, pattern=r"^[A-Za-z0-9_.\-]+$")
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    change_reason: NonEmpty = Field(max_length=300)

    @model_validator(mode="after")
    def key_actions(self):
        if self.api_key is not None:
            value = self.api_key.get_secret_value()
            if not 1 <= len(value) <= 512 or value != value.strip() or self.clear_api_key:
                raise ValueError("Invalid key operation")
        return self
