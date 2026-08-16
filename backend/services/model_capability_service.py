"""Validation-only helpers for the canonical model capability contract."""

from __future__ import annotations

from typing import Any

from schemas.model_capability_contract import ModelCapabilityContract


class CapabilityContractError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def assert_capability(
    contract: ModelCapabilityContract | None,
    *,
    purpose: str,
    expected_embedding_dimension: int | None = None,
    elapsed_seconds: float | None = None,
) -> ModelCapabilityContract:
    if contract is None or contract.purpose != purpose:
        raise CapabilityContractError("capability_missing", f"capability missing for purpose={purpose}")
    if (
        purpose == "embedding"
        and expected_embedding_dimension is not None
        and contract.embedding_dimension is not None
        and contract.embedding_dimension != expected_embedding_dimension
    ):
        raise CapabilityContractError(
            "embedding_dimension_mismatch",
            f"embedding dimension mismatch for provider={contract.provider}",
        )
    if elapsed_seconds is not None and elapsed_seconds > contract.timeout_seconds:
        raise CapabilityContractError(
            "capability_timeout",
            f"capability timeout for provider={contract.provider}",
        )
    return contract


def validate_model_response(contract: ModelCapabilityContract, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise CapabilityContractError("malformed_response", "model response must be an object")
    required_fields = contract.output_contract.get("required_fields") or []
    if not all(isinstance(field, str) and field in response for field in required_fields):
        raise CapabilityContractError("malformed_response", "model response misses required fields")
    for field, expected_type in (contract.output_contract.get("field_types") or {}).items():
        value = response.get(field)
        valid = {
            "string": isinstance(value, str),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
        }[expected_type]
        if not valid:
            raise CapabilityContractError("malformed_response", f"model response field has wrong type: {field}")
        item_type = (contract.output_contract.get("array_item_types") or {}).get(field)
        if expected_type == "array" and item_type is not None:
            item_valid = {
                "string": lambda item: isinstance(item, str),
                "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
                "boolean": lambda item: isinstance(item, bool),
                "object": lambda item: isinstance(item, dict),
                "array": lambda item: isinstance(item, list),
            }[item_type]
            if not all(item_valid(item) for item in value):
                raise CapabilityContractError("malformed_response", f"model response array items have wrong type: {field}")
    return response
