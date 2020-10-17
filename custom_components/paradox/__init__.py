"""Support for Paradox devices."""
import asyncio
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import HomeAssistantType

from .const import (DOMAIN, CONF_MODEL)
from .device import ParadoxDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistantType, config: dict):
    """Set up the SolarEnergy platform."""
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Set up Paradox from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    bridge = ParadoxDevice(hass, entry)
    if not await bridge.async_setup():
        return False

    if not bridge.available:
        raise ConfigEntryNotReady()

    hass.data[DOMAIN][entry.unique_id] = bridge
    platforms = bridge.platforms

    for component in platforms:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    bridge = hass.data[DOMAIN][entry.unique_id]
    platforms = bridge.platforms

    return all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in platforms
            ]
        )
    )
