import asyncio
import logging
from typing import Callable, List, cast
from haffmpeg.camera import CameraMjpeg
from haffmpeg.tools import IMAGE_JPEG, ImageFrame
from homeassistant.components.camera import SUPPORT_STREAM, Camera
from homeassistant.components.ffmpeg import CONF_EXTRA_ARGUMENTS, DATA_FFMPEG
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_stream

from .const import DOMAIN, CONF_MODULE, CONF_CAMERA
from .device import ParadoxDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistantType,
        config_entry: ConfigEntry,
        async_add_entities: Callable[[List[Entity], bool], None]) -> None:
    """Set up the Paradox camera video stream."""
    module = cast(ParadoxDevice, hass.data[DOMAIN][config_entry.unique_id][CONF_MODULE])

    async_add_entities(
        [ParadoxCameraEntity(module)], False
    )


class ParadoxCameraEntity(Camera):

    def __init__(self, device: ParadoxDevice) -> None:
        """Initialize Paradox camera entity."""
        self.device = device
        Camera.__init__(self)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{DOMAIN}-{self.device.device_info.serial}-{CONF_CAMERA}".lower()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.device.name

    @property
    def device_info(self):
        """Return a device description for device registry."""
        device_info = {
            "name": self.device.device_info.name,
            "identifiers": {
                # MAC address is not always available
                (DOMAIN, self.device.device_info.mac or self.device.device_info.serial)
            },
            "manufacturer": self.device.device_info.manufacturer,
            "model": self.device.device_info.model,
            "sw_version": self.device.device_info.sw_version,
        }

        if self.device.device_info.mac:
            device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, self.device.device_info.mac)
            }

        return device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.device.available

    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return SUPPORT_STREAM

    @property
    def brand(self):
        """Return the camera brand."""
        return self.device.device_info.manufacturer

    @property
    def model(self):
        """Return the camera model."""
        return self.device.device_info.model

    async def stream_source(self):
        """Return the source of the stream."""
        return await self.device.async_stream_source()

    async def async_camera_image(self):
        """Return bytes of camera image."""
        _LOGGER.debug(
            "Handling image from camera %s",
            self.device.name
        )
        stream_uri = await self.stream_source()

        ffmpeg = ImageFrame(self.hass.data[DATA_FFMPEG].binary, loop=self.hass.loop)
        image = await asyncio.shield(
            ffmpeg.get_image(
                stream_uri,
                output_format=IMAGE_JPEG,
                extra_cmd=self.device.config_entry.options.get(
                    CONF_EXTRA_ARGUMENTS
                ),
            )
        )

        return image

    async def handle_async_mjpeg_stream(self, request):
        """Serve an HTTP MJPEG stream from the camera."""
        _LOGGER.debug(
            "Handling mjpeg stream from camera %s",
            self.device.name
        )
        stream_uri = await self.stream_source()
        ffmpeg_manager = self.hass.data[DATA_FFMPEG]
        
        stream = CameraMjpeg(ffmpeg_manager.binary, loop=self.hass.loop)
        await stream.open_camera(
            stream_uri,
            extra_cmd=self.device.config_entry.options.get(CONF_EXTRA_ARGUMENTS),
        )

        try:
            stream_reader = await stream.get_reader()
            return await async_aiohttp_proxy_stream(
                self.hass,
                request,
                stream_reader,
                ffmpeg_manager.ffmpeg_stream_content_type,
            )
        finally:
            await stream.close()

    async def async_enable_recording(self):
        """Enable recording."""
        return await self.device.async_rod(3)
        # self.is_recording = True

    async def async_disable_recording(self):
        """Disable recording."""
        return await self.device.async_rod(4)
        # self.is_recording = False
