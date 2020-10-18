import logging
from typing import Callable, List, Optional, Dict, Any, cast
from homeassistant.const import (
    STATE_ALARM_DISARMED,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_CUSTOM_BYPASS,
    STATE_ALARM_PENDING,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMING,
    STATE_ALARM_TRIGGERED,
    STATE_UNKNOWN
)
import homeassistant.components.alarm_control_panel as alarm
from homeassistant.components.alarm_control_panel.const import (
    SUPPORT_ALARM_ARM_HOME,
    SUPPORT_ALARM_ARM_AWAY,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType, StateType
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, CONF_MODULE, CONF_ALARM_CONTROL_PANEL
from .device import ParadoxDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistantType,
        config_entry: ConfigEntry,
        async_add_entities: Callable[[List[Entity], bool], None]) -> None:
    """Set up the Paradox alarm panel."""
    module = cast(ParadoxDevice, hass.data[DOMAIN][config_entry.unique_id][CONF_MODULE])
    coordinator = cast(DataUpdateCoordinator, hass.data[DOMAIN][config_entry.unique_id][CONF_ALARM_CONTROL_PANEL])

    partitions = coordinator.data.get('AreaStatus', [])
    entities = [
        ParadoxAlarmEntity(module, coordinator, partition.get('AreaId'))
        for partition in partitions
    ]

    async_add_entities(entities, True)


class ParadoxAlarmEntity(alarm.AlarmControlPanelEntity):

    def __init__(self, device: ParadoxDevice, coordinator: DataUpdateCoordinator, partition_id: int) -> None:
        """Initialize Paradox camera entity."""
        self.device = device
        self._coordinator = coordinator
        self._partition_id = partition_id

        self._get_partition_from_coordinator()

    def _get_partition_from_coordinator(self) -> None:
        partitions = self._coordinator.data.get('AreaStatus', [])
        for partition in partitions:
            if partition['AreaId'] == self._partition_id:
                self._partition = partition
                return

    def should_poll(self) -> bool:
        """Not needed. Update from Data Coordinator"""
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return f"{DOMAIN}-{self.device.panel_info.serial}-{CONF_ALARM_CONTROL_PANEL}-{self._partition_id}".lower()

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return str(self._partition.get('AreaLabel')).strip()

    @property
    def state(self) -> StateType:
        """Return the state of the entity."""
        self._get_partition_from_coordinator()

        if self._partition['InAlarm']:
            return STATE_ALARM_TRIGGERED

        if self._partition['ArmingLevelID'] == 0:
            return STATE_ALARM_DISARMED

        if self._partition['ArmingLevelID'] == 1:
            return STATE_ALARM_ARMED_AWAY

        if self._partition['ArmingLevelID'] == 3:
            return STATE_ALARM_ARMED_HOME

        if self._partition['ArmingLevelID'] == 5:
            return STATE_ALARM_ARMING

        #if self._partition['ArmingLevelID'] == 0:
        #    return STATE_ALARM_PENDING

        #if self._partition['ArmingLevelID'] == 0:
        #    return STATE_ALARM_DISARMING

        return STATE_UNKNOWN

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._partition

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Return device specific attributes."""
        device_info = {
            "via_device": (DOMAIN, self.device.device_info.mac or self.device.device_info.serial),
            "name": self.device.panel_info.name,
            "identifiers": {
                # MAC address is not always available
                (DOMAIN, self.device.panel_info.mac or self.device.panel_info.serial)
            },
            "manufacturer": self.device.panel_info.manufacturer,
            "model": self.device.panel_info.model,
            "sw_version": self.device.panel_info.sw_version,
        }

        if self.device.panel_info.mac:
            device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, self.device.panel_info.mac)
            }

        return device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.device.available

    @property
    def supported_features(self) -> Optional[int]:
        """Flag supported features."""
        return SUPPORT_ALARM_ARM_HOME | SUPPORT_ALARM_ARM_AWAY

    @property
    def code_format(self):
        """Regex for code format or None if no code is required."""
        return alarm.FORMAT_TEXT

    @property
    def code_arm_required(self):
        """Whether the code is required for arm actions."""
        return False

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._coordinator.async_add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self):
        """When entity will be removed from hass."""
        self._coordinator.async_remove_listener(
            self.async_write_ha_state
        )

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""
        await self._send_alarm_command(6, code)

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""
        await self._send_alarm_command(3, code)

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        await self._send_alarm_command(2, code)

    async def _send_alarm_command(self, command: int, code=None):
        """Send alarm command."""
        area_command = {
            "AreaID": self._partition_id,
            "AreaCommand": command,
            "ForceZones": False,
        }
        await self.device.async_areacontrol([area_command])
        await self._coordinator.async_request_refresh()
