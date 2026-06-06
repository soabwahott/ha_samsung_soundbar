import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import voluptuous as vol

from .api_extension.SoundbarDevice import SoundbarDevice
from .const import DOMAIN, PLATFORMS
from .models import DeviceConfig, SoundbarConfig

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required("token"): str,
        vol.Required("device_id"): str,
        vol.Optional("name", default="Living Room Soundbar"): str,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up from configuration.yaml - token and device_id read from YAML, never hardcoded."""
    cfg = config.get(DOMAIN, {})
    token = cfg.get("token")
    device_id = cfg.get("device_id")
    device_name = cfg.get("name", "Living Room Soundbar")

    if not token or not device_id:
        _LOGGER.error("[%s] Add 'token' and 'device_id' to the %s: section in configuration.yaml", DOMAIN, DOMAIN)
        return False

    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    session = async_get_clientsession(hass)

    hass.data.setdefault(DOMAIN, SoundbarConfig(None, {}))

    soundbar = SoundbarDevice(token, device_id, session)
    await soundbar.update()

    hass.data[DOMAIN].devices[device_id] = DeviceConfig(
        {"device_id": device_id, "device_name": device_name, "token": token},
        soundbar
    )

    for platform in PLATFORMS:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    _LOGGER.info("[%s] Soundbar setup complete for device %s", DOMAIN, device_id)
    return True
