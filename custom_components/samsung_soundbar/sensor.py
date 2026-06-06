import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE

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
        async_add_entities([VolumeSensor(device)])


class VolumeSensor(SensorEntity):
    def __init__(self, device: SoundbarDevice):
        self._device = device
        self._attr_unique_id = f"{device.device_id}_sensor_volume"
        self._attr_name = f"{device.device_name} Volume"
        self._attr_icon = "mdi:volume-high"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.device_id)},
            "name": device.device_name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.firmware_version,
        }

    async def async_update(self):
        await self._device.update()
        val = self._device._volume
        self._attr_native_value = val if val is not None else None
