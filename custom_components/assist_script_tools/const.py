"""Constants for Assist Script Tools."""

from __future__ import annotations

from logging import Logger, getLogger

DOMAIN = "assist_script_tools"
LOGGER: Logger = getLogger(__package__)

CONF_SCRIPT_ENTITY_ID = "script_entity_id"
CONF_TOOL_NAME = "tool_name"
CONF_DESCRIPTION = "description"
CONF_RESOLVED_FIELDS = "resolved_fields"

DEFAULT_TOOL_DESCRIPTION = (
    "Run the configured Home Assistant script. Use human-friendly names for "
    "resolved target fields; never provide entity IDs for those fields."
)
