import os
from unittest.mock import patch

import pytest

from connectonion.cli.commands.project_cmd_lib import (
    PROVIDER_TO_ENV,
    check_environment_for_api_keys,
    configure_env_for_provider,
    detect_api_provider,
)
from connectonion.core.llm import AtlasCloudLLM, MODEL_REGISTRY, create_llm


def test_atlascloud_model_registry_and_factory_route():
    assert MODEL_REGISTRY["atlascloud/qwen/qwen3.5-flash"] == "atlascloud"
    assert MODEL_REGISTRY["atlascloud/deepseek-ai/deepseek-v4-pro"] == "atlascloud"

    with patch.dict(os.environ, {"ATLASCLOUD_API_KEY": "test-key"}):
        llm = create_llm("atlascloud/deepseek-ai/deepseek-v4-pro")

    assert isinstance(llm, AtlasCloudLLM)
    assert llm.model == "deepseek-ai/deepseek-v4-pro"


def test_atlascloud_requires_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="ATLASCLOUD_API_KEY"):
            AtlasCloudLLM(model="atlascloud/qwen/qwen3.5-flash")


def test_atlascloud_cli_provider_mapping():
    assert PROVIDER_TO_ENV["atlascloud"] == "ATLASCLOUD_API_KEY"
    assert detect_api_provider("apikey-test") == ("atlascloud", "atlascloud")

    with patch.dict(os.environ, {"ATLASCLOUD_API_KEY": "apikey-test"}, clear=True):
        assert check_environment_for_api_keys() == ("atlascloud", "apikey-test")

    env_content = configure_env_for_provider("atlascloud", "apikey-test")
    assert "ATLASCLOUD_API_KEY=apikey-test" in env_content
    assert "MODEL=atlascloud/qwen/qwen3.5-flash" in env_content
