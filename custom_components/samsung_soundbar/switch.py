import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo

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
            SoundbarSwitch(device, "nightmode", "Night Mode", "mdi:weather-night",
                           lambda d: bool(d.night_mode), device.set_night_mode),
            SoundbarSwitch(device, "bassmode", "Bass Boost", "mdi:speaker-wireless",
                           lambda d: bool(d.bass_mode), device.set_bass_mode),
            SoundbarSwitch(device, "voice_amplifier", "Voice Enhancement", "mdi:account-voice",
                           lambda d: bool(d.voice_amplifier), device.set_voice_amplifier),
        ]
        async_add_entities(entities)


class SoundbarSwitch(SwitchEntity):
    def __init__(self, device: SoundbarDevice, key: str, name: str,
                 icon: str, state_fn, on_fn):
        self._device = device
        self._key = key
        self._attr_name = f"{device.device_name} {name}"
        self._attr_unique_id = f"{device.device_id}_sw_{key}"
        self._attr_icon = icon
        self._state_fn = state_fn
        self._on_fn = on_fn
        self._state = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=device.device_name,
            manufacturer=device.manufacturer,
            model=device.model,
            sw_version=device.firmware_version,
        )

    async def async_update(self):
        try:
            await self._device.refresh_advanced_audio()
            self._state = bool(self._state_fn())
        except Exception:
            self._state = False

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self):
        await self._on_fn(True)

    async def async_turn_off(self):
        await self._on_fn(False)
