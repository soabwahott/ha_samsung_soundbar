import logging

from homeassistant.components.number import NumberEntity, NumberMode

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
        async_add_entities([WooferLevelNumber(device)])


class WooferLevelNumber(NumberEntity):
    _attr_native_min_value = -10
    _attr_native_max_value = 6
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "dB"

    def __init__(self, device: SoundbarDevice):
        self._device = device
        self._attr_unique_id = f"{device.device_id}_number_woofer"
        self._attr_name = f"{device.device_name} Woofer Level"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.device_id)},
            "name": device.device_name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.firmware_version,
        }

    @property
    def native_value(self) -> float | None:
        val = self._device.woofer_level
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float):
        await self._device.set_woofer(int(value))
