from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.model_capability_contract import (
    CapabilityErrorCode,
    ModelCapabilityContract,
    RetryPolicy,
)


def _contract(purpose: str = "chat") -> ModelCapabilityContract:
    return ModelCapabilityContract(
        provider="ollama",
        model="qwen",
        model_version="1",
        purpose=purpose,
        input_contract={"required_fields": ["messages"], "modalities": ["text"]},
        output_contract={"required_fields": ["text"], "format": "json"},
        embedding_dimension=1024 if purpose == "embedding" else None,
        context_limit=8192,
        timeout_seconds=30,
        retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1, timeout_multiplier=2.0),
        resource_class="gpu",
        capabilities=["structured_output"],
    )


@pytest.mark.parametrize("purpose", ["chat", "embedding", "vision", "rerank", "ocr"])
def test_model_capability_contract_supports_only_five_purposes(purpose: str) -> None:
    assert _contract(purpose).purpose == purpose


def test_model_capability_contract_rejects_invalid_retry_policy_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RetryPolicy(max_retries=-1, backoff_seconds=1, timeout_multiplier=2.0)
    with pytest.raises(ValidationError):
        ModelCapabilityContract(
            **_contract().model_dump(),
            unexpected="no",
        )


def test_model_capability_contract_error_codes_are_stable() -> None:
    assert set(CapabilityErrorCode) == {
        "capability_missing",
        "embedding_dimension_mismatch",
        "capability_timeout",
        "malformed_response",
    }


def test_model_capability_contract_rejects_untyped_or_malformed_io_contracts() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityContract(
            **{
                **_contract().model_dump(),
                "output_contract": {"required_fields": ["text"], "field_types": {"text": "secret"}},
            }
        )


def test_model_capability_contract_bounds_each_capability_name() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityContract(**{**_contract().model_dump(), "capabilities": ["x" * 65]})
