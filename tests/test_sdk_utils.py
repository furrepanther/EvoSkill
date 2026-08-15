from types import SimpleNamespace

from src.registry.sdk_utils import options_to_runtime_config


def test_options_to_runtime_config_normalizes_object_payload() -> None:
    options = SimpleNamespace(
        system_prompt={
            "type": "preset",
            "preset": "default_agent",
            "prepend": "before",
            "append": "after",
        },
        output_format={"type": "json_schema", "schema": {"type": "object"}},
        allowed_tools=["Read", "Write"],
        model="kilo/test-model",
        provider_id=None,
        mode="build",
    )

    payload = options_to_runtime_config(options, fallback_model="fallback-model")

    assert payload["system"] == "before\n\nafter"
    assert payload["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert payload["tools"] == {"Read": True, "Write": True}
    assert payload["model_id"] == "kilo/test-model"
    assert payload["provider_id"] == "togetherai"
    assert payload["mode"] == "build"


def test_options_to_runtime_config_passes_through_dicts() -> None:
    payload = {"system": "x", "tools": {"Read": True}}

    assert options_to_runtime_config(payload) == payload
