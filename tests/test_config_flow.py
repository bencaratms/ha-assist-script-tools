"""Tests for the Assist Script Tools config flow."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.assist_script_tools.config_flow import _validate_resolved_fields
from custom_components.assist_script_tools.const import (
    CONF_RESOLVED_FIELDS,
    CONF_SCRIPT_ENTITY_ID,
    CONF_TOOL_NAME,
    DOMAIN,
)


def test_validate_resolved_fields() -> None:
    """Accept a valid mapping."""
    assert _validate_resolved_fields(
        '[{"input_name":"speaker","script_field":"media_player_entity_id",'
        '"domains":["media_player"],"multiple":false}]'
    ) == [
        {
            "input_name": "speaker",
            "script_field": "media_player_entity_id",
            "domains": ["media_player"],
            "multiple": False,
        }
    ]


@pytest.mark.parametrize("value", ["{}", "[{}]", "not json"])
def test_validate_resolved_fields_rejects_invalid_value(value: str) -> None:
    """Reject malformed mappings."""
    with pytest.raises(vol.Invalid):
        _validate_resolved_fields(value)


async def test_user_flow_creates_script_wrapper(hass) -> None:
    """Create an entry for a configured script."""
    hass.states.async_set("script.news_flash", "off")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SCRIPT_ENTITY_ID: "script.news_flash",
            CONF_TOOL_NAME: "news_flash",
            "description": "Play the news flash on a selected speaker.",
            CONF_RESOLVED_FIELDS: (
                '[{"input_name":"speaker","script_field":"media_player_entity_id",'
                '"domains":["media_player"],"multiple":false}]'
            ),
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TOOL_NAME] == "news_flash"


async def test_user_flow_rejects_duplicate_wrapper(hass) -> None:
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
    hass.states.async_set("script.news_flash", "off")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SCRIPT_ENTITY_ID: "script.news_flash",
            CONF_TOOL_NAME: "news_flash",
            "description": "Play news.",
            CONF_RESOLVED_FIELDS: "[]",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
