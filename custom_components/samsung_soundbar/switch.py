import logging
from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .api_extension.SoundbarDevice import SoundbarDevice
from .const import DOMAIN
from .models import SoundbarConfig

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=5)



async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    domain_data: SoundbarConfig = hass.data.get(DOMAIN)
    if not domain_data:
        return

    for device_id, device_config in domain_data.devices.items():
        device: SoundbarDevice = device_config.device
        entities = [
            SoundbarSwitch(device, "nightmode", "Night Mode", "mdi:weather-night",
                           lambda d: d.night_mode, device.set_night_mode),
            SoundbarSwitch(device, "bassmode", "Bass Boost", "mdi:speaker-wireless",
                           lambda d: d.bass_mode, device.set_bass_mode),
            SoundbarSwitch(device, "voice_amplifier", "Voice Enhancement", "mdi:account-voice",
                           lambda d: d.voice_amplifier, device.set_voice_amplifier),
        ]
        async_add_entities(entities)


class SoundbarSwitch(SwitchEntity, RestoreEntity):
    def __init__(self, device: SoundbarDevice, key: str, name: str,
                 icon: str, state_fn, on_fn):
        self._device = device
        self._key = key
        self._attr_name = f"{device.device_name} {name}"
        self._attr_unique_id = f"{device.device_id}_sw_{key}"
        self._attr_icon = icon
        self._state_fn = state_fn
        self._on_fn = on_fn
        self._state = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=device.device_name,
            manufacturer=device.manufacturer,
            model=device.model,
            sw_version=device.firmware_version,
        )

    async def async_added_to_hass(self):
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ("on", "off"):
            self._state = last_state.state == "on"

    async def async_update(self):
        try:
            await self._device.refresh_advanced_audio()
            val = self._state_fn()
            if val is not None:
                self._state = bool(val)
        except Exception:
            # Keep the previous/restore state instead of claiming a false off.
            pass

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        await self._on_fn(True)
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._on_fn(False)
        self._state = False
        self.async_write_ha_state()
