"""Tests for the Assist Script Tools config flow."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.assist_script_tools.config_flow import (
    ACTION_EDIT_JSON,
    ACTION_EDIT_PARAMETER,
    ACTION_SAVE,
    MODE_MAPPED,
    ConfigFlow,
    _validate_resolved_fields,
)
from custom_components.assist_script_tools.const import (
    CONF_RESOLVED_FIELDS,
    CONF_SCRIPT_ENTITY_ID,
    CONF_TOOL_NAME,
    DOMAIN,
)

SCRIPT_FIELDS = {
    "target_entity_id": {
        "description": "Canonical entity ID to verify.",
        "domains": ["input_boolean"],
        "multiple": False,
    },
    "message": {
        "description": "Optional message for the target.",
        "domains": [],
        "multiple": False,
    },
}
MAPPING = {
    "script_field": "target_entity_id",
    "input_name": "target",
    "domains": ["input_boolean"],
    "multiple": False,
}


def test_validate_resolved_fields() -> None:
    """Accept a valid mapping."""
    assert _validate_resolved_fields(
        '[{"input_name":"target","script_field":"target_entity_id",'
        '"domains":["input_boolean"],"multiple":false}]'
    ) == [MAPPING]


@pytest.mark.parametrize("value", ["{}", "[{}]", "not json"])
def test_validate_resolved_fields_rejects_invalid_value(value: str) -> None:
    """Reject malformed mappings."""
    with pytest.raises(vol.Invalid):
        _validate_resolved_fields(value)


async def _load_test_script(flow: ConfigFlow, script_entity_id: str) -> bool:
    """Load predictable script metadata for a config-flow test."""
    flow._script_entity_id = script_entity_id
    flow._source_description = "Verify a selected target without controlling it."
    flow._script_fields = SCRIPT_FIELDS
    return True


async def _start_flow(hass) -> dict[str, object]:
    """Start the flow and reach the primary configuration form."""
    hass.states.async_set("script.verify_target_resolution", "off")
    hass.states.async_set("input_boolean.kitchen_speaker", "off")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SCRIPT_ENTITY_ID: "script.verify_target_resolution"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure"
    return result


async def test_primary_form_maps_parameter_and_creates_entry(hass) -> None:
    """Map a script parameter from the primary configuration form."""
    with patch.object(ConfigFlow, "_async_load_script", _load_test_script):
        result = await _start_flow(hass)
        assert result["data_schema"]({}) == {
            CONF_TOOL_NAME: "verify_target_resolution",
            "description": "Verify a selected target without controlling it.",
            "parameter": "target_entity_id",
            "action": ACTION_SAVE,
        }

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_TOOL_NAME: "verify_target_resolution",
                "description": "Verify a selected target without controlling it.",
                "parameter": "target_entity_id",
                "action": ACTION_EDIT_PARAMETER,
            },
        )
        assert result["step_id"] == "edit_parameter"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "mode": MODE_MAPPED,
                "input_name": MAPPING["input_name"],
                "domains": MAPPING["domains"],
                "multiple": MAPPING["multiple"],
            },
        )
        assert result["step_id"] == "configure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_TOOL_NAME: "verify_target_resolution",
                "description": "Verify a selected target without controlling it.",
                "parameter": "target_entity_id",
                "action": ACTION_SAVE,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RESOLVED_FIELDS] == [MAPPING]


async def test_json_editor_returns_to_primary_form(hass) -> None:
    """Replace mappings in JSON and return to the primary configuration form."""
    with patch.object(ConfigFlow, "_async_load_script", _load_test_script):
        result = await _start_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_TOOL_NAME: "verify_target_resolution",
                "description": "Verify a selected target without controlling it.",
                "parameter": "target_entity_id",
                "action": ACTION_EDIT_JSON,
            },
        )
        assert result["step_id"] == "advanced"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_RESOLVED_FIELDS: json.dumps([MAPPING])},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure"


async def test_duplicate_wrapper_aborts_on_save(hass) -> None:
    """Reject an existing script and tool-name combination."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="script.verify_target_resolution:verify_target_resolution",
        data={},
    ).add_to_hass(hass)

    with patch.object(ConfigFlow, "_async_load_script", _load_test_script):
        result = await _start_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_TOOL_NAME: "verify_target_resolution",
                "description": "Verify a selected target without controlling it.",
                "parameter": "target_entity_id",
                "action": ACTION_SAVE,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
