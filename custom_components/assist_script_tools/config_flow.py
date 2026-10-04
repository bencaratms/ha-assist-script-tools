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

    def __init__(self) -> None:
        """Initialize the configuration flow."""
        self._script_entity_id: str | None = None
        self._tool_name: str | None = None
        self._description: str | None = None
        self._source_description: str | None = None
        self._resolved_fields: list[dict[str, Any]] = []
        self._script_fields: dict[str, str] = {}
        self._editing_script_field: str | None = None

    async def _async_get_script_details(
        self, script_entity_id: str
    ) -> tuple[str | None, dict[str, str]]:
        """Return the description and fields exposed by the selected script."""
        script_name = split_entity_id(script_entity_id)[1]
        entity_entry = async_get_entity_registry(self.hass).async_get(script_entity_id)
        if entity_entry and entity_entry.unique_id:
            script_name = entity_entry.unique_id

        descriptions = await service.async_get_all_descriptions(self.hass)
        script_description = descriptions.get(SCRIPT_DOMAIN, {}).get(
            script_name, {}
        )
        return (
            script_description.get("description"),
            {
                field_name: field_config.get("description")
                or field_config.get("name")
                or field_name
                for field_name, field_config in script_description.get(
                    "fields", {}
                ).items()
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select the source script."""
        errors: dict[str, str] = {}

        if user_input is not None:
            script_entity_id = user_input[CONF_SCRIPT_ENTITY_ID]
            if self.hass.states.get(script_entity_id) is None:
                errors[CONF_SCRIPT_ENTITY_ID] = "script_not_found"
            else:
                source_description, script_fields = (
                    await self._async_get_script_details(script_entity_id)
                )
                if not script_fields:
                    errors[CONF_SCRIPT_ENTITY_ID] = "no_script_fields"
                else:
                    self._script_entity_id = script_entity_id
                    self._source_description = source_description
                    self._script_fields = script_fields
                    return await self.async_step_tool()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SCRIPT_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SCRIPT_DOMAIN)
                )
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_tool(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure the LLM tool's name and description."""
        assert self._script_entity_id is not None

        if user_input is not None:
            self._tool_name = user_input[CONF_TOOL_NAME]
            self._description = user_input[CONF_DESCRIPTION]
            return await self.async_step_menu()

        script_name = split_entity_id(self._script_entity_id)[1]
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_TOOL_NAME, default=script_name
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(
                    CONF_DESCRIPTION,
                    default=self._source_description or DEFAULT_TOOL_DESCRIPTION,
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT, multiline=True
                    )
                ),
            }
        )
        return self.async_show_form(step_id="tool", data_schema=data_schema)

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose how to edit target field mappings."""
        assert self._script_entity_id is not None
        assert self._tool_name is not None
        assert self._description is not None

        configured_fields = {
            mapping["script_field"] for mapping in self._resolved_fields
        }
        menu_options = ["advanced"]
        if configured_fields != set(self._script_fields):
            menu_options.insert(0, "add_field")
        if self._resolved_fields:
            menu_options.insert(-1, "edit_field")
            menu_options.append("finish")

        return self.async_show_menu(
            step_id="menu",
            menu_options=menu_options,
            description_placeholders={
                "mapped_fields": ", ".join(
                    mapping["script_field"] for mapping in self._resolved_fields
                )
                or "None",
            },
        )

    async def async_step_add_field(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one resolved script field with form controls."""
        configured_fields = {
            mapping["script_field"] for mapping in self._resolved_fields
        }
        available_fields = {
            field_name: description
            for field_name, description in self._script_fields.items()
            if field_name not in configured_fields
        }
        if not available_fields:
            return await self.async_step_menu()

        errors: dict[str, str] = {}
        if user_input is not None:
            input_name = user_input["input_name"]
            if any(
                mapping["input_name"] == input_name
                for mapping in self._resolved_fields
            ):
                errors["input_name"] = "duplicate_input_name"
            else:
                self._resolved_fields.append(
                    {
                        "input_name": input_name,
                        "script_field": user_input["script_field"],
                        "domains": user_input["domains"],
                        "multiple": user_input["multiple"],
                    }
                )
                return await self.async_step_menu()

        domains = sorted(
            {state.domain for state in self.hass.states.async_all()}
        )
        data_schema = vol.Schema(
            {
                vol.Required("script_field"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=field_name,
                                label=f"{field_name}: {description}",
                            )
                            for field_name, description in available_fields.items()
                        ]
                    )
                ),
                vol.Required("input_name"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required("domains"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=domains,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("multiple", default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="add_field", data_schema=data_schema, errors=errors
        )

    async def async_step_edit_field(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select an existing resolved field to edit."""
        if user_input is not None:
            self._editing_script_field = user_input["script_field"]
            return await self.async_step_edit_field_details()

        return self.async_show_form(
            step_id="edit_field",
            data_schema=vol.Schema(
                {
                    vol.Required("script_field"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=mapping["script_field"],
                                    label=(
                                        f"{mapping['script_field']}: "
                                        f"{mapping['input_name']}"
                                    ),
                                )
                                for mapping in self._resolved_fields
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_edit_field_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit or remove an existing resolved field."""
        assert self._editing_script_field is not None
        mapping = next(
            mapping
            for mapping in self._resolved_fields
            if mapping["script_field"] == self._editing_script_field
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input["remove"]:
                self._resolved_fields.remove(mapping)
                return await self.async_step_menu()

            input_name = user_input["input_name"]
            if any(
                existing["input_name"] == input_name and existing is not mapping
                for existing in self._resolved_fields
            ):
                errors["input_name"] = "duplicate_input_name"
            else:
                mapping.update(
                    input_name=input_name,
                    domains=user_input["domains"],
                    multiple=user_input["multiple"],
                )
                return await self.async_step_menu()

        domains = sorted(
            {state.domain for state in self.hass.states.async_all()}
        )
        data_schema = vol.Schema(
            {
                vol.Required(
                    "input_name", default=mapping["input_name"]
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(
                    "domains", default=mapping["domains"]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=domains,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    "multiple", default=mapping["multiple"]
                ): selector.BooleanSelector(),
                vol.Required("remove", default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="edit_field_details", data_schema=data_schema, errors=errors
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Replace mappings by editing their JSON representation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                resolved_fields = _validate_resolved_fields(
                    user_input[CONF_RESOLVED_FIELDS]
                )
            except vol.Invalid as err:
                errors[CONF_RESOLVED_FIELDS] = str(err)
            else:
                if {
                    mapping["script_field"] for mapping in resolved_fields
                }.difference(self._script_fields):
                    errors[CONF_RESOLVED_FIELDS] = "unknown_script_field"
                else:
                    self._resolved_fields = resolved_fields
                    return await self.async_step_menu()

        data_schema = vol.Schema(
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
        )
        return self.async_show_form(
            step_id="advanced", data_schema=data_schema, errors=errors
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
