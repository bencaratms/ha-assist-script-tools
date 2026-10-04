"""Set up Assist Script Tools."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

type AssistScriptToolsConfigEntry = ConfigEntry[None]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Assist Script Tools."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: AssistScriptToolsConfigEntry
) -> bool:
    """Set up a configured script wrapper."""
    hass.data[DOMAIN][entry.entry_id] = entry
    entry.async_on_unload(lambda: hass.data[DOMAIN].pop(entry.entry_id, None))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AssistScriptToolsConfigEntry
) -> bool:
    """Unload a configured script wrapper."""
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
