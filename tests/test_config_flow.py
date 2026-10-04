"""Tests for the Assist Script Tools config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.assist_script_tools.config_flow import (
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
    "media_player_entity_id": "Speaker for the news flash.",
    "headline": "Optional headline to announce.",
}
MAPPING = {
    "script_field": "media_player_entity_id",
    "input_name": "speaker",
    "domains": ["media_player"],
    "multiple": False,
}


def test_validate_resolved_fields() -> None:
    """Accept a valid mapping."""
    assert _validate_resolved_fields(
        '[{"input_name":"speaker","script_field":"media_player_entity_id",'
        '"domains":["media_player"],"multiple":false}]'
    ) == [MAPPING]


@pytest.mark.parametrize("value", ["{}", "[{}]", "not json"])
def test_validate_resolved_fields_rejects_invalid_value(value: str) -> None:
    """Reject malformed mappings."""
    with pytest.raises(vol.Invalid):
        _validate_resolved_fields(value)


async def _start_flow(hass) -> dict[str, object]:
    """Start a flow through the source-script form."""
    hass.states.async_set("script.news_flash", "off")
    hass.states.async_set("media_player.kitchen_speaker", "idle")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCRIPT_ENTITY_ID: "script.news_flash"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tool"
    assert result["data_schema"]({}) == {
        CONF_TOOL_NAME: "news_flash",
        "description": "Play the news flash on a selected speaker.",
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TOOL_NAME: "news_flash",
            "description": "Play the news flash on a selected speaker.",
        },
    )
    assert result["type"] is FlowResultType.MENU
    assert "finish" not in result["menu_options"]
    return result


async def _add_field(hass, flow_id: str) -> dict[str, object]:
    """Add the standard resolved speaker field."""
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "add_field"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_field"

    result = await hass.config_entries.flow.async_configure(flow_id, MAPPING)
    assert result["type"] is FlowResultType.MENU
    return result


async def test_guided_flow_creates_script_wrapper(hass) -> None:
    """Create an entry with the guided resolved-field form."""
    with patch.object(
        ConfigFlow,
        "_async_get_script_details",
        return_value=("Play the news flash on a selected speaker.", SCRIPT_FIELDS),
    ):
        result = await _start_flow(hass)
        result = await _add_field(hass, result["flow_id"])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "finish"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RESOLVED_FIELDS] == [MAPPING]


async def test_advanced_json_replaces_guided_mappings(hass) -> None:
    """Use the Advanced JSON editor after adding a guided mapping."""
    with patch.object(
        ConfigFlow,
        "_async_get_script_details",
        return_value=("Play the news flash on a selected speaker.", SCRIPT_FIELDS),
    ):
        result = await _start_flow(hass)
        result = await _add_field(hass, result["flow_id"])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "advanced"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "advanced"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_RESOLVED_FIELDS: (
                    '[{"input_name":"headline_target",'
                    '"script_field":"headline",'
                    '"domains":["media_player"],'
                    '"multiple":false}]'
                )
            },
        )
        assert result["type"] is FlowResultType.MENU
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "edit_field"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"script_field": "headline"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "edit_field_details"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "input_name": "announcement_target",
                "domains": ["media_player"],
                "multiple": False,
                "remove": False,
            },
        )
        assert result["type"] is FlowResultType.MENU
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "finish"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RESOLVED_FIELDS] == [
        {
            "input_name": "announcement_target",
            "script_field": "headline",
            "domains": ["media_player"],
            "multiple": False,
        }
    ]


async def test_guided_flow_rejects_duplicate_wrapper(hass) -> None:
    """Do not create duplicate script wrappers."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="script.news_flash:news_flash",
        data={
            CONF_SCRIPT_ENTITY_ID: "script.news_flash",
            CONF_TOOL_NAME: "news_flash",
            "description": "Play news.",
            CONF_RESOLVED_FIELDS: [],
        },
    ).add_to_hass(hass)

    with patch.object(
        ConfigFlow,
        "_async_get_script_details",
        return_value=("Play the news flash on a selected speaker.", SCRIPT_FIELDS),
    ):
        result = await _start_flow(hass)
        result = await _add_field(hass, result["flow_id"])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "finish"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
