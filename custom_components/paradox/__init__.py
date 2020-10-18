"""Support for Paradox devices."""
import asyncio
import logging
from typing import cast
from datetime import timedelta
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (DOMAIN, CONF_MODEL, CONF_MODULE, DEFAULT_SCAN_INTERVAL, CONF_ALARM_CONTROL_PANEL)
from .device import ParadoxDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistantType, config: dict):
    """Set up the SolarEnergy platform."""
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Set up Paradox from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    module = ParadoxDevice(hass, entry)
    if not await module.async_setup():
        return False

    if not module.available:
        raise ConfigEntryNotReady()

    platforms = module.platforms
    hass.data[DOMAIN][entry.unique_id] = {
        CONF_MODULE: module
    }

    if CONF_ALARM_CONTROL_PANEL in platforms:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        coordinator = ParadoxAlarmPanelUpdateCoordinator(hass, module, scan_interval)
        await coordinator.async_refresh()
        hass.data[DOMAIN][entry.unique_id][CONF_ALARM_CONTROL_PANEL] = coordinator

    for component in platforms:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    module = cast(ParadoxDevice, hass.data[DOMAIN][entry.unique_id][CONF_MODULE])
    platforms = module.platforms

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in platforms
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok


class ParadoxAlarmPanelUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching alarm panel data."""

    def __init__(self, hass: HomeAssistantType, module: ParadoxDevice, scan_interval: int):
        """Initialize alarm panel data updater."""

        self.device = module
        interval = timedelta(seconds=scan_interval)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{CONF_ALARM_CONTROL_PANEL}",
            update_interval=interval,
        )

    async def _async_update_data(self):
        """Fetch data from Paradox module."""
        return await self.device.async_update_alarm_panel()
