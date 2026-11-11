import pytest

from app.modules.executions.runtime import ProviderFailure, _openai_usage


@pytest.mark.parametrize("value", [-1, True, "12"])
def test_tool_harness_rejects_invalid_usage_instead_of_crediting_budget(value):
    with pytest.raises(ProviderFailure):
        _openai_usage({"status": "completed", "usage": {"input_tokens": value, "output_tokens": 2}})
