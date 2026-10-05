"""Tests for resolved script tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import voluptuous as vol
from homeassistant.core import State
from homeassistant.helpers import intent
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.llm import LLMContext, ToolInput

from custom_components.assist_script_tools.const import (
    CONF_DESCRIPTION,
    CONF_RESOLVED_FIELDS,
    CONF_SCRIPT_ENTITY_ID,
    CONF_TOOL_NAME,
)
from custom_components.assist_script_tools.llm import ResolvedScriptTool


def _entry_data() -> dict[str, object]:
    """Return a configured news-flash wrapper."""
    return {
        CONF_SCRIPT_ENTITY_ID: "script.news_flash",
        CONF_TOOL_NAME: "news_flash",
        CONF_DESCRIPTION: "Play a news flash.",
        CONF_RESOLVED_FIELDS: [
            {
                "input_name": "speaker",
                "script_field": "media_player_entity_id",
                "domains": ["media_player"],
                "multiple": False,
            }
        ],
    }


async def test_tool_resolves_name_before_calling_script(hass) -> None:
    """Pass the canonical ID, rather than the LLM-facing friendly name."""
    source_tool = MagicMock()
    source_tool.name = "script__news_flash"
    source_tool.parameters = vol.Schema(
        {
            vol.Required(
                "media_player_entity_id", description="Speaker for the news flash."
            ): str
        }
    )
    source_tool.async_call = AsyncMock(
        return_value={"success": True, "result": {"started": True}}
    )
    match_result = SimpleNamespace(
        is_match=True,
        states=[
            State(
                "media_player.kitchen_speaker",
                "idle",
                {"friendly_name": "Kitchen Speaker"},
            )
        ],
        no_match_reason=None,
    )
    llm_context = LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant="conversation",
        device_id=None,
    )

    with (
        patch(
            "custom_components.assist_script_tools.llm.ScriptTool",
            return_value=source_tool,
        ),
        patch(
            "custom_components.assist_script_tools.llm.intent.async_match_targets",
            return_value=match_result,
        ) as match_targets,
    ):
        tool = ResolvedScriptTool(hass, _entry_data())
        parameter = next(iter(tool.parameters.schema))
        result = await tool.async_call(
            hass,
            ToolInput(
                tool_name=tool.name,
                tool_args={"speaker": "Kitchen Speaker"},
            ),
            llm_context,
        )

    assert result["success"] is True
    assert parameter.description == (
        "Speaker for the news flash.\n\n"
        "Human-friendly name of the media_player target. "
        "Do not provide an entity ID."
    )
    assert result["resolved_targets"] == {
        "speaker": [
            {
                "entity_id": "media_player.kitchen_speaker",
                "name": "Kitchen Speaker",
            }
        ]
    }
    assert match_targets.call_args.args[1].domains == {"media_player"}
    assert source_tool.async_call.call_args.args[1].tool_args == {
        "media_player_entity_id": "media_player.kitchen_speaker"
    }


async def test_tool_restricts_target_resolution_to_integrations(hass) -> None:
    """Pass only states belonging to the configured integration to Core."""
    entry_data = _entry_data()
    entry_data[CONF_RESOLVED_FIELDS][0]["integrations"] = ["music_assistant"]
    entity_registry = async_get_entity_registry(hass)
    music_assistant_entity = entity_registry.async_get_or_create(
        "media_player",
        "music_assistant",
        "kitchen_speaker",
        suggested_object_id="kitchen_speaker",
    )
    sonos_entity = entity_registry.async_get_or_create(
        "media_player",
        "sonos",
        "other_speaker",
        suggested_object_id="other_speaker",
    )
    hass.states.async_set(music_assistant_entity.entity_id, "idle")
    hass.states.async_set(sonos_entity.entity_id, "idle")
    source_tool = MagicMock()
    source_tool.name = "script__news_flash"
    source_tool.parameters = vol.Schema(
        {vol.Required("media_player_entity_id"): str}
    )
    source_tool.async_call = AsyncMock(return_value={"success": True})
    match_result = SimpleNamespace(
        is_match=True,
        states=[hass.states.get(music_assistant_entity.entity_id)],
        no_match_reason=None,
    )
    llm_context = LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant="conversation",
        device_id=None,
    )

    with (
        patch(
            "custom_components.assist_script_tools.llm.ScriptTool",
            return_value=source_tool,
        ),
        patch(
            "custom_components.assist_script_tools.llm.intent.async_match_targets",
            return_value=match_result,
        ) as match_targets,
    ):
        tool = ResolvedScriptTool(hass, entry_data)
        await tool.async_call(
            hass,
            ToolInput(
                tool_name=tool.name,
                tool_args={"speaker": "Kitchen Speaker"},
            ),
            llm_context,
        )

    assert [
        state.entity_id for state in match_targets.call_args.kwargs["states"]
    ] == [music_assistant_entity.entity_id]


async def test_tool_does_not_call_script_when_target_is_unresolved(hass) -> None:
    """Return a tool error instead of guessing an entity ID."""
    source_tool = MagicMock()
    source_tool.name = "script__news_flash"
    source_tool.parameters = vol.Schema(
        {vol.Required("media_player_entity_id"): str}
    )
    source_tool.async_call = AsyncMock()
    match_result = SimpleNamespace(
        is_match=False,
        states=[],
        no_match_reason=intent.MatchFailedReason.ASSISTANT,
    )
    llm_context = LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant="conversation",
        device_id=None,
    )

    with (
        patch(
            "custom_components.assist_script_tools.llm.ScriptTool",
            return_value=source_tool,
        ),
        patch(
            "custom_components.assist_script_tools.llm.intent.async_match_targets",
            return_value=match_result,
        ),
    ):
        tool = ResolvedScriptTool(hass, _entry_data())
        result = await tool.async_call(
            hass,
            ToolInput(
                tool_name=tool.name,
                tool_args={"speaker": "Kitchen Speaker"},
            ),
            llm_context,
        )

    assert result["success"] is False
    assert result["error"] == "target_not_resolved"
    assert result["reason"] == "assistant"
    source_tool.async_call.assert_not_awaited()
