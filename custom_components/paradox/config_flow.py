"""Adds config flow for Paradox integration."""
import logging
import voluptuous as vol
from typing import Any, Dict, Optional, List
from asyncio.exceptions import TimeoutError
from aiohttp import ClientConnectionError
from pypdxapi.helpers import discover_modules
from pypdxapi.exceptions import ParadoxModuleError
from homeassistant.config_entries import (CONN_CLASS_LOCAL_POLL, ConfigEntry, ConfigFlow, OptionsFlow)
from homeassistant.const import (CONF_NAME, CONF_HOST, CONF_PORT, CONF_TIMEOUT, CONF_USERNAME, CONF_PASSWORD,
                                 CONF_DEVICE, CONF_DOMAIN, CONF_DOMAINS)
from homeassistant.components.ffmpeg import CONF_EXTRA_ARGUMENTS
from homeassistant.core import callback
from homeassistant.helpers.typing import (HomeAssistantType, ConfigType)
import homeassistant.helpers.config_validation as cv

from .const import (DOMAIN, CONF_MODEL, CONF_USERCODE, DEFAULT_PORT, DEFAULT_PASSWORD, DEFAULT_USERNAME,
                    DEFAULT_USERCODE, DEFAULT_TIMEOUT,
                    CONF_CAMERA, CAMERA_PROFILES, CONF_CAMERA_PROFILE, DEFAULT_CAMERA_PROFILE,
                    DEFAULT_FFMPEG_ARGUMENTS,)
from .models import SupportedModuleInfo, DiscoveredModuleInfo
from .device import get_device_cls

CONF_MANUAL_INPUT = "Manually configure Paradox module"

_LOGGER = logging.getLogger(__name__)


SUPPORTED_MODELS = {
    'HD77': SupportedModuleInfo(
        default_domain=[
            "camera"
        ],
        supported_domains=[
            "alarm_control_panel",
            "binary_sensor",
            "switch",
        ],
    )
}


async def async_discovery(hass: HomeAssistantType) -> List[DiscoveredModuleInfo]:
    """Return if there are devices that can be discovered."""
    _LOGGER.debug("Starting Paradox module discovery...")
    modules: List[dict] = await hass.async_add_executor_job(discover_modules)

    devices: List[DiscoveredModuleInfo] = []
    for module in modules:
        if module['type'] in list(SUPPORTED_MODELS.keys()):
            device = DiscoveredModuleInfo(
                name=str(module['ZoneLabel']).strip() if 'ZoneLabel' else str(module['sitename']).strip(),
                model=module['type'],
                serial=module['sn'],
                host=module['ip'],
                port=module['portweb'],
                mac=module['mac']
            )

            devices.append(device)
        else:
            _LOGGER.error("Discover a Paradox module not compatible: %s", module)

    return devices


class ParadoxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Paradox."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ParadoxOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.device_id = None
        self.device_config = {}
        self.discovered_devices: List[DiscoveredModuleInfo] = []

    async def async_step_user(self, user_input: Optional[ConfigType] = None):
        """Handle user flow."""
        if user_input is not None:
            return await self.async_step_device()

        return self.async_show_form(step_id="user")

    async def async_step_device(self, user_input: Optional[ConfigType] = None) -> Dict[str, Any]:
        """Handle Paradox module discover.

        Let user choose between discovered devices and manual configuration.
        If no device is found allow user to manually input configuration.
        """
        if user_input is not None:
            if CONF_MANUAL_INPUT == user_input[CONF_NAME]:
                return await self.async_step_manual_input()

            for device in self.discovered_devices:
                name = f"{device.model} {device.name}"
                if name == user_input[CONF_NAME]:
                    self.device_id = f"{DOMAIN}-{device.serial}".lower()
                    self.device_config = {
                        CONF_NAME: device.name,
                        CONF_MODEL: device.model,
                        CONF_HOST: device.host,
                        CONF_PORT: device.port,
                        CONF_PASSWORD: None,
                    }

                    return await self.async_step_auth()

        discovery = await async_discovery(self.hass)
        for device in discovery:
            configured = any(
                entry.unique_id == f"{DOMAIN}-{device.serial}".lower()
                for entry in self._async_current_entries()
            )

            if not configured:
                self.discovered_devices.append(device)

        if self.discovered_devices:
            names = [
                f"{device.model} {device.name}" for device in self.discovered_devices
            ]
            names.append(CONF_MANUAL_INPUT)

            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_NAME): vol.In(names)
                    }
                ),
            )

        return await self.async_step_manual_input()

    async def async_step_manual_input(
            self,
            user_input: Optional[ConfigType] = None) -> Dict[str, Any]:
        """Manual configuration."""
        errors = {}

        if user_input is None:
            model = None
            host = ''
            port = DEFAULT_PORT
            password = DEFAULT_PASSWORD
        else:
            model = user_input.get(CONF_MODEL)
            host = user_input.get(CONF_HOST)
            port = user_input.get(CONF_PORT)
            password = user_input.get(CONF_PASSWORD)

            try:
                module = get_device_cls(self.hass, model, host, port, password)
                info = await module.pingstatus()

                configured = any(
                    entry.unique_id == f"{DOMAIN}-{info['SerialNumber']}".lower()
                    for entry in self._async_current_entries()
                )
                if configured:
                    return self.async_abort(reason="already_configured_device")

                self.device_id = f"{DOMAIN}-{info['SerialNumber']}".lower()
                self.device_config = {
                    CONF_NAME: None,
                    CONF_MODEL: model,
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_PASSWORD: password
                }

                return await self.async_step_auth()

            except ParadoxModuleError:
                errors["base"] = "invalid_auth"
            except (ClientConnectionError, TimeoutError):
                errors["base"] = "cannot_connect"
            except NotImplementedError:
                _LOGGER.exception("Unexpected exception")
                return self.async_abort(reason="unknown_reason")

        return self.async_show_form(
            step_id="manual_input",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MODEL,
                        default=model
                    ): vol.In(list(SUPPORTED_MODELS.keys())),
                    vol.Required(
                        CONF_HOST,
                        default=host
                    ): str,
                    vol.Required(
                        CONF_PORT,
                        default=port
                    ): int,
                    vol.Required(
                        CONF_PASSWORD,
                        default=password
                    ): str,
                }
            ),
            errors=errors or {},
        )

    async def async_step_auth(self, user_input: Optional[ConfigType] = None) -> Dict[str, Any]:
        """Username and Password configuration."""
        errors = {}

        if user_input is None:
            password = DEFAULT_PASSWORD
            username = DEFAULT_USERNAME
            usercode = DEFAULT_USERCODE
        else:
            password = user_input.get(CONF_PASSWORD, self.device_config.get(CONF_PASSWORD))
            username = user_input.get(CONF_USERNAME)
            usercode = user_input.get(CONF_USERCODE)

            model = self.device_config.get(CONF_MODEL)
            host = self.device_config.get(CONF_HOST)
            port = self.device_config.get(CONF_PORT)

            try:
                module = get_device_cls(self.hass, model, host, port, password)
                await module.login(usercode, username)

                if self.device_config[CONF_NAME] is None:
                    self.device_config[CONF_NAME] = module.name
                if self.device_config[CONF_PASSWORD] is None:
                    self.device_config[CONF_PASSWORD] = password
                self.device_config[CONF_USERNAME] = username
                self.device_config[CONF_USERCODE] = usercode

                await self.async_set_unique_id(self.device_id, raise_on_progress=False)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: self.device_config[CONF_HOST],
                        CONF_PORT: self.device_config[CONF_PORT],
                        CONF_PASSWORD: self.device_config[CONF_PASSWORD],
                        CONF_USERNAME: self.device_config[CONF_USERNAME],
                        CONF_USERCODE: self.device_config[CONF_USERCODE]
                    }
                )

                self.device_config[CONF_DOMAIN] = SUPPORTED_MODELS[model].default_domain
                title = f"{self.device_config[CONF_MODEL]} {self.device_config[CONF_NAME]}"
                return self.async_create_entry(title=title, data=self.device_config)

            except ParadoxModuleError:
                errors["base"] = "invalid_auth"
            except NotImplementedError:
                _LOGGER.exception("Unexpected exception")
                return self.async_abort(reason="unknown_reason")

        data = {}
        if self.device_config.get(CONF_PASSWORD) is None:
            data.update(
                {
                    vol.Required(
                        CONF_PASSWORD,
                        default=password
                    ): str,
                }
            )
        data.update(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=username
                ): str,
                vol.Required(
                    CONF_USERCODE,
                    default=usercode
                ): str,
            }
        )

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(data),
            errors=errors or {},
        )


class ParadoxOptionsFlowHandler(OptionsFlow):
    """Handle Paradox module options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self._steps = []

    async def async_step_init(self, user_input: Optional[ConfigType] = None):

        if user_input is not None:
            self.options[CONF_DEVICE] = user_input.copy()
            self._steps = self.config_entry.data[CONF_DOMAIN] + user_input.get(CONF_DOMAINS, [])

            return await self._next_step()

        options = self.config_entry.options.get(CONF_DEVICE, {})
        default_domains = options.get(CONF_DOMAINS, [])
        default_timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        model = self.config_entry.data.get(CONF_MODEL)
        supported_domains = SUPPORTED_MODELS[model].supported_domains

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DOMAINS,
                        default=default_domains
                    ): cv.multi_select(supported_domains),
                    vol.Required(
                        CONF_TIMEOUT,
                        default=default_timeout,
                    ): int,
                }
            ),
        )

    async def async_step_camera(self, user_input: Optional[ConfigType] = None):
        """Manage Paradox camera options."""

        if user_input is not None:
            self.options[CONF_CAMERA] = user_input.copy()

            return await self._next_step()

        options = self.config_entry.options.get(CONF_CAMERA, {})
        default_camera_profile = options.get(CONF_CAMERA_PROFILE, DEFAULT_CAMERA_PROFILE)
        default_extra_arguments = options.get(CONF_EXTRA_ARGUMENTS, DEFAULT_FFMPEG_ARGUMENTS)

        return self.async_show_form(
            step_id="camera",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CAMERA_PROFILE,
                        default=default_camera_profile,
                    ): vol.In(CAMERA_PROFILES),
                    vol.Required(
                        CONF_EXTRA_ARGUMENTS,
                        default=default_extra_arguments,
                    ): str,
                }
            ),
        )

    async def _next_step(self):
        if 'camera' in self._steps:
            self._steps.pop(self._steps.index(CONF_CAMERA))
            return await self.async_step_camera()

        return self.async_create_entry(title="", data=self.options)
