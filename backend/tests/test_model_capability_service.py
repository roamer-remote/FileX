from __future__ import annotations

import pytest

from schemas.model_capability_contract import ModelCapabilityContract, RetryPolicy
from services.model_capability_service import (
    CapabilityContractError,
    assert_capability,
    validate_model_response,
)


def _contract() -> ModelCapabilityContract:
    return ModelCapabilityContract(
        provider="ollama",
        model="embed",
        model_version="1",
        purpose="embedding",
        input_contract={"required_fields": ["text"]},
        output_contract={"required_fields": ["vector"]},
        embedding_dimension=1024,
        context_limit=None,
        timeout_seconds=2,
        retry_policy=RetryPolicy(max_retries=1, backoff_seconds=1, timeout_multiplier=2.0),
        resource_class="gpu",
        capabilities=["batch"],
    )


def test_capability_validation_reports_missing_and_dimension_errors_without_fallback() -> None:
    with pytest.raises(CapabilityContractError) as missing:
        assert_capability(None, purpose="embedding")
    assert missing.value.code == "capability_missing"

    with pytest.raises(CapabilityContractError) as mismatch:
        assert_capability(_contract(), purpose="embedding", expected_embedding_dimension=768)
    assert mismatch.value.code == "embedding_dimension_mismatch"


def test_capability_validation_reports_timeout_and_malformed_response() -> None:
    with pytest.raises(CapabilityContractError) as timeout:
        assert_capability(_contract(), purpose="embedding", elapsed_seconds=3)
    assert timeout.value.code == "capability_timeout"

    with pytest.raises(CapabilityContractError) as malformed:
        validate_model_response(_contract(), {"text": "wrong"})
    assert malformed.value.code == "malformed_response"


def test_embedding_dimension_unknown_is_not_treated_as_mismatch() -> None:
    contract = _contract().model_copy(update={"embedding_dimension": None})
    assert assert_capability(contract, purpose="embedding", expected_embedding_dimension=768) == contract


def test_capability_validation_checks_declared_output_field_types() -> None:
    contract = _contract().model_copy(
        update={"output_contract": {"required_fields": ["vector"], "field_types": {"vector": "array"}}}
    )
    with pytest.raises(CapabilityContractError) as malformed:
        validate_model_response(contract, {"vector": "not-an-array"})
    assert malformed.value.code == "malformed_response"
