import asyncio
import datetime
import json
import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

SMARTTHINGS_BASE = "https://api.smartthings.com/v1"


class SoundbarDevice:
    def __init__(self, token: str, device_id: str, session):
        self._token = token
        self._device_id = device_id
        self._session = session
        self._max_volume = 100
        self._device_name = "Living Room Soundbar"

        self._night_mode = 0
        self._bass_mode = 0
        self._voice_amplifier = 0
        self._woofer_level = 0
        self._woofer_connection = ""
        self._sound_mode = ""
        self._supported_soundmodes = []
        self._eq_preset = ""
        self._supported_eq_presets = []
        self._media_title = ""
        self._media_artist = ""
        self._media_cover_url = ""
        self._media_cover_url_update_time = None
        self._old_media_title = ""

        self._state = "on"
        self._volume = 0
        self._muted = False
        self._input_source = "digital"

        self._manufacturer = "Samsung"
        self._model = "HW-S60B"
        self._firmware_version = "unknown"

    async def _api_get(self, path: str):
        url = SMARTTHINGS_BASE + path
        headers = {"Authorization": f"Bearer {self._token}"}
        async with self._session.get(url, headers=headers) as resp:
            data = await resp.json()
            if not resp.ok:
                log.error("[soundbar] API GET %s failed: %s", path, data)
            return data

    async def _api_post(self, path: str, json_data: dict):
        url = SMARTTHINGS_BASE + path
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        async with self._session.post(url, headers=headers, json=json_data) as resp:
            data = await resp.json()
            if not resp.ok:
                log.error("[soundbar] API POST %s failed: %s", path, data)
            return data

    async def update(self):
        """Poll device status from SmartThings."""
        device_data = await self._api_get(f"/devices/{self._device_id}/status")
        if "components" not in device_data:
            log.warning("[soundbar] Device status returned: %s", device_data)
            return

        comp = device_data["components"].get("main", {})

        # Power / state
        switch = comp.get("switch", {})
        if switch.get("switch", {}).get("value") == "on":
            self._state = "playing"
        else:
            self._state = "off"

        # Volume
        volume = comp.get("volume", {})
        self._volume = volume.get("level", {}).get("value", 0)
        mute = comp.get("mute", {})
        self._muted = mute.get("mute", {}).get("value") == "muted"

        # Input source
        audio = comp.get("audioInputSource", {})
        src = audio.get("inputSource", {})
        self._input_source = src.get("value", "digital")

        # Media info
        track = comp.get("audioTrackData", {})
        track_data = track.get("audioTrackData", {}).get("value", {})
        self._media_artist = track_data.get("artist", "")
        self._media_title = track_data.get("title", "")
        if self._media_title and self._media_title != self._old_media_title:
            self._old_media_title = self._media_title
            self._media_cover_url_update_time = datetime.datetime.now()
            self._media_cover_url = await self._fetch_artwork(
                self._media_artist, self._media_title
            )

        # Device info
        ocf = comp.get("ocf", {})
        self._manufacturer = ocf.get("ocf.manufacturerName", {}).get("value", "Samsung")
        self._model = ocf.get("ocf.modelNumber", {}).get("value", "HW-S60B")
        self._firmware_version = ocf.get("ocf.firmwareVersion", {}).get("value", "unknown")

        # Samsung Audio API: advanced audio (night mode, bass, voice)
        await self._update_advanced_audio()
        # Sound mode
        await self._update_soundmode()
        # Woofer
        await self._update_woofer()

    async def _update_advanced_audio(self):
        await self._execute(["/sec/networkaudio/advancedaudio"])
        await asyncio.sleep(0.5)
        payload = await self._get_execute_status()
        if "x.com.samsung.networkaudio.nightmode" in payload:
            self._night_mode = payload["x.com.samsung.networkaudio.nightmode"]
            self._bass_mode = payload["x.com.samsung.networkaudio.bassboost"]
            self._voice_amplifier = payload["x.com.samsung.networkaudio.voiceamplifier"]

    async def _update_soundmode(self):
        await self._execute(["/sec/networkaudio/soundmode"])
        await asyncio.sleep(0.5)
        payload = await self._get_execute_status()
        if "x.com.samsung.networkaudio.soundmode" in payload:
            self._sound_mode = payload["x.com.samsung.networkaudio.soundmode"]
            self._supported_soundmodes = payload.get(
                "x.com.samsung.networkaudio.supportedSoundmode", []
            )

    async def _update_woofer(self):
        await self._execute(["/sec/networkaudio/woofer"])
        await asyncio.sleep(0.3)
        payload = await self._get_execute_status()
        if "x.com.samsung.networkaudio.woofer" in payload:
            self._woofer_level = payload["x.com.samsung.networkaudio.woofer"]
            self._woofer_connection = payload.get("x.com.samsung.networkaudio.connection", "")

    async def _execute(self, argument):
        """Trigger Samsung Audio API resource path."""
        path = f"/devices/{self._device_id}/components/main/capabilities/execute/executions"
        await self._api_post(path, {"commands": [{"component": "main", "capability": "execute", "command": "execute", "arguments": argument}]})

    async def _get_execute_status(self) -> dict:
        """Poll Samsung Audio API status endpoint."""
        path = f"/devices/{self._device_id}/components/main/capabilities/execute/status"
        data = await self._api_get(path)
        if "data" in data:
            value = data["data"].get("value", {})
            if isinstance(value, dict) and "payload" in value:
                return value["payload"]
        return {}

    async def _sam_write(self, href: str, property_name: str, value):
        """Write Samsung Audio API property."""
        await self._execute([href])
        await asyncio.sleep(0.3)
        path = f"/devices/{self._device_id}/components/main/capabilities/execute/executions"
        await self._api_post(path, {
            "commands": [{
                "component": "main",
                "capability": "execute",
                "command": "execute",
                "arguments": [href, {property_name: value}]
            }]
        })

    async def _fetch_artwork(self, artist: str, title: str) -> str:
        if not artist or not title:
            return ""
        query = quote(f"{artist} {title}")
        url = f"https://itunes.apple.com/search?term={query}&media=music&entity=musicTrack&limit=1"
        try:
            async with self._session.get(url) as resp:
                data = await resp.json()
                results = data.get("results", [])
                if results:
                    return results[0].get("artworkUrl100", "")
        except Exception:
            pass
        return ""

    # -------- Properties --------

    @property
    def device_id(self): return self._device_id
    @property
    def device_name(self): return self._device_name
    @property
    def manufacturer(self): return self._manufacturer
    @property
    def model(self): return self._model
    @property
    def firmware_version(self): return self._firmware_version

    @property
    def state(self) -> str:
        return self._state

    @property
    def volume_level(self) -> float:
        vol = self._volume
        if vol > self._max_volume:
            return 1.0
        return vol / self._max_volume

    @property
    def volume_muted(self) -> bool:
        return self._muted

    async def set_volume(self, volume: float):
        level = int(volume * self._max_volume)
        path = f"/devices/{self._device_id}/components/main/capabilities/volume/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "setVolume", "arguments": [level]}]
        })

    async def mute_volume(self, mute: bool):
        path = f"/devices/{self._device_id}/components/main/capabilities/mute/execute"
        cmd = "mute" if mute else "unmute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": cmd, "arguments": []}]
        })

    async def volume_up(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/audioNotification/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "playFeedback", "arguments": [{"type": "volume", "command": "increase"}]}]
        })

    async def volume_down(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/audioNotification/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "playFeedback", "arguments": [{"type": "volume", "command": "decrease"}]}]
        })

    async def switch_off(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/switch/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "off", "arguments": []}]
        })

    async def switch_on(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/switch/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "on", "arguments": []}]
        })

    @property
    def input_source(self): return self._input_source

    @property
    def supported_input_sources(self): return ["digital", "bluetooth", "wifi"]

    async def select_source(self, source: str):
        # Firmware blocks input switching (HTTP 422)
        log.warning("[soundbar] Input source switching is blocked by firmware")

    @property
    def sound_mode(self): return self._sound_mode
    @property
    def supported_soundmodes(self): return self._supported_soundmodes

    async def select_sound_mode(self, sound_mode: str):
        await self._sam_write("/sec/networkaudio/soundmode",
                               "x.com.samsung.networkaudio.soundmode", sound_mode)

    @property
    def night_mode(self) -> bool: return self._night_mode == 1

    async def set_night_mode(self, value: bool):
        await self._sam_write("/sec/networkaudio/advancedaudio",
                               "x.com.samsung.networkaudio.nightmode", 1 if value else 0)

    @property
    def bass_mode(self) -> bool: return self._bass_mode == 1

    async def set_bass_mode(self, value: bool):
        await self._sam_write("/sec/networkaudio/advancedaudio",
                               "x.com.samsung.networkaudio.bassboost", 1 if value else 0)

    @property
    def voice_amplifier(self) -> bool: return self._voice_amplifier == 1

    async def set_voice_amplifier(self, value: bool):
        await self._sam_write("/sec/networkaudio/advancedaudio",
                               "x.com.samsung.networkaudio.voiceamplifier", 1 if value else 0)

    @property
    def woofer_level(self) -> int: return self._woofer_level
    @property
    def woofer_connection(self) -> str: return self._woofer_connection

    async def set_woofer(self, level: int):
        await self._sam_write("/sec/networkaudio/woofer",
                               "x.com.samsung.networkaudio.woofer", level)

    @property
    def active_equalizer_preset(self): return self._eq_preset
    @property
    def supported_equalizer_presets(self): return self._supported_eq_presets
    async def set_equalizer_preset(self, preset: str):
        await self._sam_write("/sec/networkaudio/eq",
                               "x.com.samsung.networkaudio.EQname", preset)

    @property
    def media_title(self): return self._media_title
    @property
    def media_artist(self): return self._media_artist
    @property
    def media_coverart_url(self): return self._media_cover_url
    @property
    def media_coverart_updated(self): return self._media_cover_url_update_time

    @property
    def media_duration(self) -> int | None: return None
    @property
    def media_position(self) -> int | None: return None

    async def media_play(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/mediaPlayback/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "play", "arguments": []}]
        })

    async def media_pause(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/mediaPlayback/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "pause", "arguments": []}]
        })

    async def media_stop(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/mediaPlayback/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "stop", "arguments": []}]
        })

    async def media_next_track(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/mediaPlayback/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "fastForward", "arguments": []}]
        })

    async def media_previous_track(self):
        path = f"/devices/{self._device_id}/components/main/capabilities/mediaPlayback/execute"
        await self._api_post(path, {
            "commands": [{"component": "main", "capability": "execute", "command": "rewind", "arguments": []}]
        })
