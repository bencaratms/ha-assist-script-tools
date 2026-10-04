"""LLM tools that safely invoke configured Home Assistant scripts."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol
from homeassistant.components.llm import LLMTools
from homeassistant.components.script.llm import ScriptTool
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolInput,
)

from .const import (
    CONF_DESCRIPTION,
    CONF_RESOLVED_FIELDS,
    CONF_SCRIPT_ENTITY_ID,
    CONF_TOOL_NAME,
    DOMAIN,
)


class ResolvedScriptTool(Tool):
    """Wrap a script tool with Core target resolution."""

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        """Initialize the configured wrapper."""
        self._source = ScriptTool(hass, entry_data[CONF_SCRIPT_ENTITY_ID])
        self._resolved_fields: list[dict[str, Any]] = entry_data[CONF_RESOLVED_FIELDS]
        self.name = f"{DOMAIN}__{entry_data[CONF_TOOL_NAME]}"
        self.title = entry_data[CONF_TOOL_NAME].replace("_", " ").title()
        self.description = entry_data[CONF_DESCRIPTION]

        source_schema = dict(self._source.parameters.schema)
        schema: dict[Any, Any] = {}
        resolved_script_fields = {
            mapping["script_field"] for mapping in self._resolved_fields
        }
        source_descriptions = {
            str(field): field.description
            for field in source_schema
            if isinstance(field, vol.Marker)
        }
        for key, validator in source_schema.items():
            field_name = str(key)
            if field_name not in resolved_script_fields:
                schema[key] = validator

        for mapping in self._resolved_fields:
            resolution_description = (
                f"Human-friendly name of the {', '.join(mapping['domains'])} target. "
                "Do not provide an entity ID."
            )
            if source_description := source_descriptions.get(
                mapping["script_field"]
            ):
                description = f"{source_description}\n\n{resolution_description}"
            else:
                description = resolution_description
            field = vol.Required(mapping["input_name"], description=description)
            schema[field] = [str] if mapping["multiple"] else str

        self.parameters = vol.Schema(schema)

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> dict[str, Any]:
        """Resolve targets and call the configured script."""
        script_args = dict(tool_input.tool_args)
        resolved_targets: dict[str, list[dict[str, str]]] = {}

        for mapping in self._resolved_fields:
            input_name = mapping["input_name"]
            script_field = mapping["script_field"]
            values = script_args.pop(input_name)
            names = values if mapping["multiple"] else [values]
            entity_ids: list[str] = []
            matched: list[dict[str, str]] = []

            for name in names:
                constraints = intent.MatchTargetsConstraints(
                    name=name,
                    domains=set(mapping["domains"]),
                    assistant=llm_context.assistant,
                    single_target=not mapping["multiple"],
                )
                result = intent.async_match_targets(
                    hass, constraints, intent.MatchTargetsPreferences()
                )
                if not result.is_match:
                    return {
                        "success": False,
                        "error": "target_not_resolved",
                        "field": input_name,
                        "target": name,
                        "reason": result.no_match_reason.value
                        if result.no_match_reason
                        else "unknown",
                    }

                for state in result.states:
                    entity_ids.append(state.entity_id)
                    matched.append({"entity_id": state.entity_id, "name": state.name})

            script_args[script_field] = (
                entity_ids if mapping["multiple"] else entity_ids[0]
            )
            resolved_targets[input_name] = matched

        result = await self._source.async_call(
            hass,
            ToolInput(
                tool_name=self._source.name,
                tool_args=script_args,
                id=tool_input.id,
                external=tool_input.external,
            ),
            llm_context,
        )
        return {
            "success": result.get("success", True),
            "resolved_targets": resolved_targets,
            "script_result": result.get("result"),
        }


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return configured script wrappers for the Assist API."""
    if api_id != LLM_API_ASSIST:
        return None

    entries = hass.data.get(DOMAIN, {}).values()
    tools = [
        ResolvedScriptTool(hass, entry.data)
        for entry in entries
        if hass.states.get(entry.data[CONF_SCRIPT_ENTITY_ID]) is not None
    ]
    return LLMTools(tools=tools) if tools else None
