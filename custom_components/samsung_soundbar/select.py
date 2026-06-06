import logging

from homeassistant.components.select import SelectEntity

from .api_extension.SoundbarDevice import SoundbarDevice
from .const import DOMAIN
from .models import SoundbarConfig

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    domain_data: SoundbarConfig = hass.data.get(DOMAIN)
    if not domain_data:
        return

    for device_id, device_config in domain_data.devices.items():
        device: SoundbarDevice = device_config.device
        entities = [
            SoundModeSelect(device),
            InputSourceSelect(device),
        ]
        async_add_entities(entities)


class SoundModeSelect(SelectEntity):
    def __init__(self, device: SoundbarDevice):
        self._device = device
        self._attr_unique_id = f"{device.device_id}_select_soundmode"
        self._attr_name = f"{device.device_name} Sound Mode"
        self._attr_icon = "mdi:surround-sound"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.device_id)},
            "name": device.device_name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.firmware_version,
        }

    async def async_update(self):
        await self._device.refresh_soundmode()

    @property
    def options(self) -> list[str]:
        opts = self._device.supported_soundmodes
        return opts if opts else []

    @property
    def current_option(self) -> str | None:
        val = self._device.sound_mode
        return val if val else None

    async def async_select_option(self, option: str):
        await self._device.select_sound_mode(option)


class InputSourceSelect(SelectEntity):
    def __init__(self, device: SoundbarDevice):
        self._device = device
        self._attr_unique_id = f"{device.device_id}_select_input"
        self._attr_name = f"{device.device_name} Input Source"
        self._attr_icon = "mdi:video-input-hdmi"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.device_id)},
            "name": device.device_name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.firmware_version,
        }

    @property
    def options(self) -> list[str]:
        return self._device.supported_input_sources

    @property
    def current_option(self) -> str | None:
        val = self._device.input_source
        return val if val else None

    async def async_select_option(self, option: str):
        await self._device.select_source(option)
