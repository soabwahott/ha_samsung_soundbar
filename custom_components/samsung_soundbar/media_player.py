import logging
from datetime import timedelta

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.helpers.entity import DeviceInfo

from .api_extension.SoundbarDevice import SoundbarDevice
from .api_extension.const import SpeakerIdentifier, RearSpeakerMode
from .const import DOMAIN
from .models import SoundbarConfig

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=5)


SUPPORT_FEATURES = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.SELECT_SOUND_MODE
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    domain_data: SoundbarConfig = hass.data.get(DOMAIN)
    if not domain_data:
        return

    for device_id, device_config in domain_data.devices.items():
        device: SoundbarDevice = device_config.device
        async_add_entities([SoundbarMediaPlayer(device)])


class SoundbarMediaPlayer(MediaPlayerEntity):
    def __init__(self, device: SoundbarDevice):
        self._device = device
        self._attr_unique_id = f"{device.device_id}_mp"
        self._attr_name = device.device_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=device.device_name,
            manufacturer=device.manufacturer,
            model=device.model,
            sw_version=device.firmware_version,
        )

    async def async_update(self):
        await self._device.update()

    @property
    def supported_features(self):
        return SUPPORT_FEATURES

    @property
    def state(self):
        return self._device.state

    async def async_turn_off(self):
        await self._device.switch_off()

    async def async_turn_on(self):
        await self._device.switch_on()

    @property
    def volume_level(self) -> float | None:
        return self._device.volume_level

    @property
    def is_volume_muted(self) -> bool | None:
        return self._device.volume_muted

    async def async_set_volume_level(self, volume: float):
        await self._device.set_volume(volume)
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool):
        await self._device.mute_volume(mute)
        self.async_write_ha_state()

    async def async_volume_up(self):
        await self._device.volume_up()
        self.async_write_ha_state()

    async def async_volume_down(self):
        await self._device.volume_down()
        self.async_write_ha_state()

    @property
    def source(self) -> str | None:
        return self._device.input_source

    @property
    def source_list(self) -> list[str] | None:
        return self._device.supported_input_sources

    async def async_select_source(self, source: str):
        await self._device.select_source(source)

    @property
    def sound_mode(self) -> str | None:
        return self._device.sound_mode

    @property
    def sound_mode_list(self) -> list[str] | None:
        return self._device.supported_soundmodes

    async def async_select_sound_mode(self, sound_mode: str):
        await self._device.select_sound_mode(sound_mode)

    @property
    def media_title(self) -> str | None:
        return self._device.media_title

    @property
    def media_artist(self) -> str | None:
        return self._device.media_artist

    @property
    def media_image_url(self) -> str | None:
        return self._device.media_coverart_url

    async def async_media_play(self):
        await self._device.media_play()

    async def async_media_pause(self):
        await self._device.media_pause()

    async def async_media_stop(self):
        await self._device.media_stop()

    async def async_media_next_track(self):
        await self._device.media_next_track()

    async def async_media_previous_track(self):
        await self._device.media_previous_track()

    # Extra services (mirror from switch/number entities for convenience)
    async def async_set_night_mode(self, enabled: bool):
        await self._device.set_night_mode(enabled)

    async def async_set_bass_mode(self, enabled: bool):
        await self._device.set_bass_mode(enabled)

    async def async_set_voice_mode(self, enabled: bool):
        await self._device.set_voice_amplifier(enabled)

    async def async_set_woofer_level(self, level: int):
        await self._device.set_woofer(level)
