from __future__ import annotations

import os
from unittest.mock import patch

from src.driver.run_autogen_pipeline import _experiment_default_model


def test_experiment_defaults_pin_supported_models() -> None:
    with patch.dict(
        os.environ,
        {
            "FIREWORKS_MODEL": "deepseek-v4-pro",
            "FIREWORKS_MODELS": "deepseek-v4-pro,accounts/fireworks/models/deepseek-v3p2",
        },
        clear=True,
    ):
        assert _experiment_default_model("fireworks") == "accounts/fireworks/models/gpt-oss-120b"
        assert _experiment_default_model("fireworks_ai") == "accounts/fireworks/models/gpt-oss-120b"
        assert _experiment_default_model("mistral") == "mistral-small-latest"


def test_experiment_defaults_do_not_remove_backend_provider_support() -> None:
    assert _experiment_default_model("groq") is None
    assert _experiment_default_model("azure") is None
