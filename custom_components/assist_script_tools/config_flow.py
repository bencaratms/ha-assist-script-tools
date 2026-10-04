"""Config flow for Assist Script Tools."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.const import CONF_DESCRIPTION
from homeassistant.helpers import selector

from .const import (
    CONF_RESOLVED_FIELDS,
    CONF_SCRIPT_ENTITY_ID,
    CONF_TOOL_NAME,
    DEFAULT_TOOL_DESCRIPTION,
    DOMAIN,
)


def _validate_resolved_fields(value: str) -> list[dict[str, Any]]:
    """Validate target-field mapping JSON."""
    try:
        mappings = json.loads(value)
    except json.JSONDecodeError as err:
        raise vol.Invalid("invalid_json") from err

    if not isinstance(mappings, list):
        raise vol.Invalid("not_a_list")

    input_names: set[str] = set()
    script_fields: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise vol.Invalid("invalid_mapping")

        input_name = mapping.get("input_name")
        script_field = mapping.get("script_field")
        domains = mapping.get("domains")
        multiple = mapping.get("multiple", False)
        if (
            not isinstance(input_name, str)
            or not input_name.isidentifier()
            or not isinstance(script_field, str)
            or not script_field.isidentifier()
            or not isinstance(domains, list)
            or not domains
            or not all(
                isinstance(domain, str) and domain.isidentifier()
                for domain in domains
            )
            or not isinstance(multiple, bool)
            or input_name in input_names
            or script_field in script_fields
        ):
            raise vol.Invalid("invalid_mapping")

        input_names.add(input_name)
        script_fields.add(script_field)

    return mappings


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a script wrapper."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure a script wrapper."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                resolved_fields = _validate_resolved_fields(
                    user_input[CONF_RESOLVED_FIELDS]
                )
            except vol.Invalid as err:
                errors[CONF_RESOLVED_FIELDS] = str(err)
            else:
                script_entity_id = user_input[CONF_SCRIPT_ENTITY_ID]
                if self.hass.states.get(script_entity_id) is None:
                    errors[CONF_SCRIPT_ENTITY_ID] = "script_not_found"
                else:
                    await self.async_set_unique_id(
                        f"{script_entity_id}:{user_input[CONF_TOOL_NAME]}"
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_TOOL_NAME].replace("_", " ").title(),
                        data={
                            CONF_SCRIPT_ENTITY_ID: script_entity_id,
                            CONF_TOOL_NAME: user_input[CONF_TOOL_NAME],
                            CONF_DESCRIPTION: user_input[CONF_DESCRIPTION],
                            CONF_RESOLVED_FIELDS: resolved_fields,
                        },
                    )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SCRIPT_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SCRIPT_DOMAIN)
                ),
                vol.Required(CONF_TOOL_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(
                    CONF_DESCRIPTION, default=DEFAULT_TOOL_DESCRIPTION
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT, multiline=True
                    )
                ),
                vol.Required(CONF_RESOLVED_FIELDS, default="[]"): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT, multiline=True
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )
