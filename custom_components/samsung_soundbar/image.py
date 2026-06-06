import logging
from datetime import datetime

from homeassistant.components.image import ImageEntity

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
        async_add_entities([SoundbarArtwork(device, hass)])


class SoundbarArtwork(ImageEntity):
    def __init__(self, device: SoundbarDevice, hass):
        super().__init__(hass)
        self._device = device
        self._attr_unique_id = f"{device.device_id}_image_artwork"
        self._attr_name = f"{device.device_name} Album Art"
        self._cached_url = None

    @property
    def image_url(self) -> str | None:
        url = self._device.media_coverart_url
        if url and url != self._cached_url:
            self._cached_url = url
        return url if url else None

    @property
    def image_last_updated(self) -> datetime | None:
        return self._device.media_coverart_updated
