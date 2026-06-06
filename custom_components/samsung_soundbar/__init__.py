import logging
import os

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .api_extension.SoundbarDevice import SoundbarDevice
from .const import DOMAIN, PLATFORMS
from .models import DeviceConfig, SoundbarConfig

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up from environment variables (no config flow needed)."""
    token = os.environ.get("SMARTTHINGS_TOKEN")
    if not token:
        _LOGGER.error("[%s] SMARTTHINGS_TOKEN not set in environment", DOMAIN)
        return False

    device_id = os.environ.get("SMARTTHINGS_DEVICE_ID", "71aabf81-c4de-8d2c-d3d3-b9668a488fac")
    device_name = os.environ.get("SMARTTHINGS_DEVICE_NAME", "Living Room Soundbar")

    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    session = async_get_clientsession(hass)

    hass.data.setdefault(DOMAIN, SoundbarConfig(None, {}))

    soundbar = SoundbarDevice(token, device_id, session)
    await soundbar.update()

    hass.data[DOMAIN].devices[device_id] = DeviceConfig(
        {"device_id": device_id, "device_name": device_name, "api_key": token},
        soundbar
    )

    for platform in PLATFORMS:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    _LOGGER.info("[%s] Soundbar setup complete for device %s", DOMAIN, device_id)
    return True


# No async_setup_entry needed (config_flow: false)
