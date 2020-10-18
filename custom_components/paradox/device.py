"""Paradox module abstraction."""
import logging
from typing import List, Optional
from asyncio.exceptions import TimeoutError
from aiohttp import ClientConnectionError
from pypdxapi.exceptions import ParadoxModuleError
from pypdxapi.camera import ParadoxHD77
import m3u8
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_NAME, CONF_HOST, CONF_PORT, CONF_TIMEOUT, CONF_USERNAME, CONF_PASSWORD,
                                 CONF_DEVICE, CONF_DOMAIN, CONF_DOMAINS)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (MANUFACTURER, CONF_MODEL, CONF_USERCODE, DEFAULT_TIMEOUT,
                    CONF_CAMERA, CONF_CAMERA_PROFILE, DEFAULT_CAMERA_PROFILE, CAMERA_BANDWIDTH)
from .models import DeviceInfo

_LOGGER = logging.getLogger(__name__)


def get_device_cls(hass: HomeAssistant, model: str, host: str, port: int, module_password: str,
                   timeout: int = DEFAULT_TIMEOUT):
    adapter_cls = eval(f"Paradox{model}")
    client_session = hass.helpers.aiohttp_client.async_get_clientsession()

    return adapter_cls(
        host=host, port=port, module_password=module_password,
        client_session=client_session,
        request_timeout=timeout,
        raise_on_result_code_error=True
    )


class ParadoxDevice:
    """Manages an Paradox device."""
    device = None
    _available: bool = False
    _device_info: DeviceInfo = None
    # Alarm
    _panel_info: DeviceInfo = None
    # Camera
    _last_stream_source = None

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry = None):
        """Initialize"""
        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry
        self._options = config_entry.options.get(CONF_DEVICE, {})

    @property
    def model(self) -> str:
        """Return the model of this module."""
        return self.config_entry.data[CONF_MODEL]

    @property
    def name(self) -> str:
        """Return the name of this module."""
        return self.config_entry.data[CONF_NAME]

    @property
    def host(self) -> str:
        """Return the host of this module."""
        return self.config_entry.data[CONF_HOST]

    @property
    def port(self) -> int:
        """Return the port of this module."""
        return self.config_entry.data[CONF_PORT]

    @property
    def password(self) -> str:
        """Return the password of this device."""
        return self.config_entry.data[CONF_PASSWORD]

    @property
    def username(self) -> str:
        """Return the username of alarm panel."""
        return self.config_entry.data[CONF_USERNAME]

    @property
    def usercode(self) -> str:
        """Return the usercode of alarm panel."""
        return self.config_entry.data[CONF_USERCODE]

    @property
    def available(self) -> bool:
        """ Return module available."""
        return self._available

    @property
    def device_info(self) -> DeviceInfo:
        """ Return module info."""
        return self._device_info

    @property
    def panel_info(self) -> DeviceInfo:
        """ Return module info."""
        return self._panel_info

    @property
    def platforms(self) -> List:
        """ Return supported platforms."""
        return self.config_entry.data[CONF_DOMAIN] + self._options.get(CONF_DOMAINS, [])

    async def async_setup(self) -> bool:
        """Set up the device."""
        timeout = self._options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            self.device = get_device_cls(self.hass, self.model, self.host, self.port, self.password, timeout=timeout)
            data = await self.device.login(self.usercode, self.username)

            self._device_info = DeviceInfo(
                manufacturer=MANUFACTURER,
                model=self.model,
                name=self.name,
                sw_version=self.device.version,
                serial=self.device.serial,
                mac=None
            )
            self._panel_info = DeviceInfo(
                manufacturer=MANUFACTURER,
                model='',
                name='Paradox Control Panel',
                sw_version=f"{data['ParadoxCP']['Version']}.{data['ParadoxCP']['Revision']}",
                serial=data['ParadoxCP']['SerialNo'],
                mac=None
            )

            self._available = True

        except (ClientConnectionError, TimeoutError):
            _LOGGER.error(
                "Couldn't connect to device '%s', but will retry later.",
                self.name
            )
        except ParadoxModuleError:
            _LOGGER.error(
                "Couldn't connect to device '%s', please verify that the credentials are correct.",
                self.name
            )
            return False
        except NotImplementedError:
            _LOGGER.exception(
                "Couldn't connect to device '%s'. Unexpected exception.",
                self.name
            )

        return True

    async def async_stream_source(self) -> Optional[str]:
        """ Calls video on demand and obtains the stream url according to the quality channel.
        API returns m3u8 playlist file and Home Assistant is not adaptive and always get the
        first segment (low quality). Then I use a parse to get the selected channel.

        :return: (str) Url
        """
        try:
            if not self.device.is_authenticated():
                self._last_stream_source = None
                await self.device.login(username=self.username, usercode=self.usercode)

            if self._last_stream_source is None:
                options = self.config_entry.options.get(CONF_CAMERA, {})
                channel_type = options.get(CONF_CAMERA_PROFILE, DEFAULT_CAMERA_PROFILE)
                bandwidth = CAMERA_BANDWIDTH[channel_type]
                _LOGGER.debug("Channel type: %s", bandwidth)

                m3u8_file = await self.device.vod(channel_type=channel_type.lower())
                variant_m3u8 = m3u8.loads(m3u8_file)

                for playlist in variant_m3u8.playlists:
                    if playlist.stream_info.bandwidth == bandwidth:
                        self._last_stream_source = playlist.uri
                        break

            return self._last_stream_source

        except (ClientConnectionError, TimeoutError):
            self._last_stream_source = None
            _LOGGER.error(
                "Couldn't get stream url from camera '%s', but will retry later.",
                self.name
            )
        except ParadoxModuleError:
            self._available = False
            _LOGGER.error(
                "Couldn't get stream url from camera '%s', please verify that the credentials are correct. ",
                self.name
            )
        except NotImplementedError:
            _LOGGER.exception(
                "Couldn't get stream url from camera '%s'. Unexpected exception.",
                self.name
            )

        return ''

    async def async_update_alarm_panel(self) -> dict:
        """ Fetch alarm panel data

        :return: dict data from module
        """
        try:
            return await self.device.pingstatus()

        except (ClientConnectionError, TimeoutError) as error:
            _LOGGER.error(
                "Couldn't fetch alarm panel data from module '%s'.",
                self.name
            )
            raise UpdateFailed(error) from error
        except ParadoxModuleError as error:
            self._available = False
            _LOGGER.error(
                "Couldn't fetch alarm panel data from module '%s', please verify that the credentials are correct. ",
                self.name
            )
            raise UpdateFailed(error) from error
        except NotImplementedError as error:
            _LOGGER.exception(
                "Couldn't fetch alarm panel data from module '%s'. Unexpected exception.",
                self.name
            )
            raise UpdateFailed(error) from error

    async def async_areacontrol(self, area_commands: List[dict]) -> bool:
        """ Control Areas

        :param area_commands: AreaID
        :return: True/False
        """
        try:
            if not self.device.is_authenticated():
                await self.device.login(username=self.username, usercode=self.usercode)

            await self.device.areacontrol(area_commands)
            return True

        except (ClientConnectionError, TimeoutError):
            _LOGGER.exception(
                "Couldn't send command to alarm panel from module '%s'.",
                self.name
            )
        except ParadoxModuleError:
            self._available = False
            _LOGGER.error(
                "Couldn't send command to alarm panel from module '%s', "
                "please verify that the credentials are correct. ",
                self.name
            )
        except NotImplementedError:
            _LOGGER.exception(
                "Couldn't send command to alarm panel from module '%s'. Unexpected exception.",
                self.name
            )

        return False

    async def async_rod(self, state: int) -> bool:
        """ Start/Stop record on demand

        :param state: 3 -> Start, 4 -> Stop
        :return: bool
        """
        try:
            if not self.device.is_authenticated():
                await self.device.login(username=self.username, usercode=self.usercode)

            data = await self.device.rod(action=state)
            return data['ResultCode'] == 33816578

        except (ClientConnectionError, TimeoutError):
            _LOGGER.error(
                "Couldn't set record on demand from camera '%s'.",
                self.name
            )
        except ParadoxModuleError:
            self._available = False
            _LOGGER.error(
                "Couldn't set record on demand from camera '%s', please verify that the credentials are correct. ",
                self.name
            )
        except NotImplementedError:
            _LOGGER.exception(
                "Couldn't set record on demand from camera '%s'. Unexpected exception.",
                self.name
            )

        return False
