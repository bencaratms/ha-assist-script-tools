"""Tests for config-flow translations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

TRANSLATION_FILES = (
    Path("custom_components/assist_script_tools/strings.json"),
    Path("custom_components/assist_script_tools/translations/en.json"),
)


def _string_values(value: Any) -> list[str]:
    """Return all string values from a decoded translation document."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            string
            for nested_value in value.values()
            for string in _string_values(nested_value)
        ]
    return []


@pytest.mark.parametrize("translation_file", TRANSLATION_FILES)
def test_config_flow_translations_do_not_use_format_arguments(
    translation_file: Path,
) -> None:
    """Avoid frontend message-format parsing for static config-flow text."""
    translations = json.loads(translation_file.read_text(encoding="utf-8"))

    assert all(
        "{" not in value and "}" not in value
        for value in _string_values(translations["config"])
    )
