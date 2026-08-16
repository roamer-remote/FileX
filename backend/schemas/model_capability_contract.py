"""Canonical provider/model capability contract for 187-P1."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapabilityErrorCode(StrEnum):
    CAPABILITY_MISSING = "capability_missing"
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"
    CAPABILITY_TIMEOUT = "capability_timeout"
    MALFORMED_RESPONSE = "malformed_response"


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(ge=0)
    backoff_seconds: int = Field(ge=0)
    timeout_multiplier: float | None = Field(default=None, gt=0)


class ModelCapabilityContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["187.1"] = "187.1"
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    model_version: str = Field(min_length=1, max_length=128)
    purpose: Literal["chat", "embedding", "vision", "rerank", "ocr"]
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    embedding_dimension: int | None = Field(default=None, gt=0)
    context_limit: int | None = Field(default=None, gt=0)
    timeout_seconds: float = Field(gt=0)
    retry_policy: RetryPolicy
    resource_class: str | None = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_io_contracts(self) -> "ModelCapabilityContract":
        if any(not isinstance(capability, str) or not 1 <= len(capability) <= 64 for capability in self.capabilities):
            raise ValueError("capabilities must contain non-empty strings of at most 64 characters")
        for name, contract in (("input_contract", self.input_contract), ("output_contract", self.output_contract)):
            if not isinstance(contract, dict):
                raise ValueError(f"{name} must be an object")
            required = contract.get("required_fields")
            if not isinstance(required, list) or not required or not all(
                isinstance(field, str) and 1 <= len(field) <= 64 for field in required
            ):
                raise ValueError(f"{name}.required_fields must be a non-empty string list")
            field_types = contract.get("field_types", {})
            if not isinstance(field_types, dict) or any(
                not isinstance(field, str) or kind not in {"string", "number", "boolean", "object", "array"}
                for field, kind in field_types.items()
            ):
                raise ValueError(f"{name}.field_types contains an unsupported type")
            if any(field not in required for field in field_types):
                raise ValueError(f"{name}.field_types must describe required fields only")
            array_item_types = contract.get("array_item_types", {})
            if not isinstance(array_item_types, dict) or any(
                field not in field_types or field_types[field] != "array"
                or kind not in {"string", "number", "boolean", "object", "array"}
                for field, kind in array_item_types.items()
            ):
                raise ValueError(f"{name}.array_item_types contains an unsupported type")
        return self
