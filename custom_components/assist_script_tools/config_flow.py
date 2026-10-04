"""Config flow for Assist Script Tools."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.const import CONF_DESCRIPTION
from homeassistant.core import split_entity_id
from homeassistant.helpers import selector, service
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import (
    CONF_RESOLVED_FIELDS,
    CONF_SCRIPT_ENTITY_ID,
    CONF_TOOL_NAME,
    DEFAULT_TOOL_DESCRIPTION,
    DOMAIN,
)

ACTION_SAVE = "save"
ACTION_EDIT_PARAMETER = "edit_parameter"
ACTION_EDIT_JSON = "edit_json"
MODE_MAPPED = "mapped"
MODE_PASSTHROUGH = "passthrough"


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
        input_name = mapping.get("input_name") if isinstance(mapping, dict) else None
        script_field = (
            mapping.get("script_field") if isinstance(mapping, dict) else None
        )
        domains = mapping.get("domains") if isinstance(mapping, dict) else None
        multiple = mapping.get("multiple", False) if isinstance(mapping, dict) else None
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

    def __init__(self) -> None:
        """Initialize the configuration flow."""
        self._script_entity_id: str | None = None
        self._tool_name: str | None = None
        self._description: str | None = None
        self._source_description: str | None = None
        self._resolved_fields: list[dict[str, Any]] = []
        self._script_fields: dict[str, dict[str, Any]] = {}
        self._editing_script_field: str | None = None

    async def _async_load_script(self, script_entity_id: str) -> bool:
        """Load the source script's metadata and parameters."""
        if self.hass.states.get(script_entity_id) is None:
            return False

        script_name = split_entity_id(script_entity_id)[1]
        entity_entry = async_get_entity_registry(self.hass).async_get(script_entity_id)
        if entity_entry and entity_entry.unique_id:
            script_name = entity_entry.unique_id

        descriptions = await service.async_get_all_descriptions(self.hass)
        script = descriptions.get(SCRIPT_DOMAIN, {}).get(script_name, {})
        fields = script.get("fields", {})
        if not fields:
            return False

        self._script_entity_id = script_entity_id
        self._source_description = script.get("description")
        self._script_fields = {
            name: {
                "description": config.get("description")
                or config.get("name")
                or name,
                "domains": self._selector_domains(config),
                "multiple": self._selector_multiple(config),
            }
            for name, config in fields.items()
        }
        return True

    @staticmethod
    def _selector_domains(field: dict[str, Any]) -> list[str]:
        """Return entity-domain defaults declared by a script field."""
        entity_config = field.get("selector", {}).get("entity", {})
        domains = entity_config.get("domain", [])
        return [domains] if isinstance(domains, str) else domains

    @staticmethod
    def _selector_multiple(field: dict[str, Any]) -> bool:
        """Return the multiple-target default declared by a script field."""
        return bool(field.get("selector", {}).get("entity", {}).get("multiple", False))

    def _mapping_for(self, script_field: str) -> dict[str, Any] | None:
        """Return the mapping for one script field."""
        return next(
            (
                mapping
                for mapping in self._resolved_fields
                if mapping["script_field"] == script_field
            ),
            None,
        )

    def _available_domains(self) -> list[str]:
        """Return domains available to map from the current Home Assistant state."""
        return sorted({state.domain for state in self.hass.states.async_all()})

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select the source script before opening the configuration form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if await self._async_load_script(user_input[CONF_SCRIPT_ENTITY_ID]):
                return await self.async_step_configure()
            errors[CONF_SCRIPT_ENTITY_ID] = (
                "script_not_found"
                if self.hass.states.get(user_input[CONF_SCRIPT_ENTITY_ID]) is None
                else "no_script_fields"
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCRIPT_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=SCRIPT_DOMAIN)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure the tool and select the next native flow action."""
        assert self._script_entity_id is not None

        errors: dict[str, str] = {}
        if user_input is not None:
            self._tool_name = user_input[CONF_TOOL_NAME]
            self._description = user_input[CONF_DESCRIPTION]
            action = user_input["action"]
            if action == ACTION_EDIT_PARAMETER:
                self._editing_script_field = user_input["parameter"]
                return await self.async_step_edit_parameter()
            if action == ACTION_EDIT_JSON:
                return await self.async_step_advanced()
            return await self.async_step_finish()

        defaults = self._script_fields
        selected_parameter = next(iter(defaults))
        script_name = split_entity_id(self._script_entity_id)[1]
        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TOOL_NAME, default=self._tool_name or script_name
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        CONF_DESCRIPTION,
                        default=(
                            self._description
                            or self._source_description
                            or DEFAULT_TOOL_DESCRIPTION
                        ),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT, multiline=True
                        )
                    ),
                    vol.Required(
                        "parameter", default=selected_parameter
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=name,
                                    label=self._parameter_label(name, field),
                                )
                                for name, field in defaults.items()
                            ]
                        )
                    ),
                    vol.Required(
                        "action", default=ACTION_SAVE
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=ACTION_SAVE, label="Save tool"
                                ),
                                selector.SelectOptionDict(
                                    value=ACTION_EDIT_PARAMETER,
                                    label="Edit selected parameter",
                                ),
                                selector.SelectOptionDict(
                                    value=ACTION_EDIT_JSON,
                                    label="Edit mappings as JSON",
                                ),
                            ]
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_parameter(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure one script parameter as pass-through or mapped."""
        assert self._editing_script_field is not None
        field_name = self._editing_script_field
        field = self._script_fields[field_name]
        mapping = self._mapping_for(field_name)
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input["mode"] == MODE_PASSTHROUGH:
                if mapping:
                    self._resolved_fields.remove(mapping)
                return await self.async_step_configure()

            input_name = user_input["input_name"]
            if any(
                existing["input_name"] == input_name and existing is not mapping
                for existing in self._resolved_fields
            ):
                errors["input_name"] = "duplicate_input_name"
            else:
                new_mapping = {
                    "input_name": input_name,
                    "script_field": field_name,
                    "domains": user_input["domains"],
                    "multiple": user_input["multiple"],
                }
                if mapping:
                    mapping.update(new_mapping)
                else:
                    self._resolved_fields.append(new_mapping)
                return await self.async_step_configure()

        default_domains = (
            mapping["domains"]
            if mapping
            else field["domains"] or self._available_domains()
        )
        return self.async_show_form(
            step_id="edit_parameter",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "mode",
                        default=MODE_MAPPED if mapping else MODE_PASSTHROUGH,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=MODE_PASSTHROUGH, label="Pass through"
                                ),
                                selector.SelectOptionDict(
                                    value=MODE_MAPPED, label="Resolve a target"
                                ),
                            ]
                        )
                    ),
                    vol.Required(
                        "input_name",
                        default=mapping["input_name"] if mapping else field_name,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        "domains", default=default_domains
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._available_domains(),
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        "multiple",
                        default=mapping["multiple"] if mapping else field["multiple"],
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors,
        )

    def _parameter_label(self, name: str, field: dict[str, Any]) -> str:
        """Create the native selector label for a script parameter."""
        status = "mapped" if self._mapping_for(name) else "pass-through"
        return f"{name} ({status}): {field['description']}"

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Replace mappings by editing their JSON representation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                mappings = _validate_resolved_fields(user_input[CONF_RESOLVED_FIELDS])
            except vol.Invalid as err:
                errors[CONF_RESOLVED_FIELDS] = str(err)
            else:
                if {mapping["script_field"] for mapping in mappings}.difference(
                    self._script_fields
                ):
                    errors[CONF_RESOLVED_FIELDS] = "unknown_script_field"
                else:
                    self._resolved_fields = mappings
                    return await self.async_step_configure()

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RESOLVED_FIELDS,
                        default=json.dumps(self._resolved_fields, indent=2),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT, multiline=True
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create the configured script wrapper."""
        assert self._script_entity_id is not None
        assert self._tool_name is not None
        assert self._description is not None

        await self.async_set_unique_id(f"{self._script_entity_id}:{self._tool_name}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._tool_name.replace("_", " ").title(),
            data={
                CONF_SCRIPT_ENTITY_ID: self._script_entity_id,
                CONF_TOOL_NAME: self._tool_name,
                CONF_DESCRIPTION: self._description,
                CONF_RESOLVED_FIELDS: self._resolved_fields,
            },
        )
