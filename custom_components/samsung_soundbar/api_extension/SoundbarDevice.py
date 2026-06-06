import asyncio
import datetime
import json
import logging
import time
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

        self._night_mode = None
        self._bass_mode = None
        self._voice_amplifier = None
        self._woofer_level = 0
        self._woofer_connection = ""
        self._sound_mode = ""
        self._supported_soundmodes = ["standard", "surround", "game", "adaptive"]
        self._supported_input_sources = ["digital", "bluetooth", "wifi"]
        self._media_title = ""
        self._media_artist = ""
        self._media_cover_url = ""
        self._media_cover_url_update_time = None
        self._old_media_title = ""

        self._state = "on"
        self._volume = 0
        self._muted = False
        self._volume_hold_until = 0.0
        self._mute_hold_until = 0.0
        self._input_source = "digital"

        self._manufacturer = "Samsung"
        self._model = "HW-S60B"
        self._firmware_version = "unknown"

        self._advanced_audio_last_refresh = 0.0
        self._soundmode_last_refresh = 0.0
        self._woofer_last_refresh = 0.0
        self._advanced_audio_lock = asyncio.Lock()
        self._soundmode_lock = asyncio.Lock()
        self._woofer_lock = asyncio.Lock()

    # -------- Core API helpers (matching working standalone script) --------

    async def _api(self, method: str, path: str, data: dict | None = None):
        """Low-level API call - uses /commands endpoint pattern (same as working script)."""
        url = SMARTTHINGS_BASE + path
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = json.dumps(data).encode() if data else None

        try:
            async with self._session.request(method, url, headers=headers, data=body) as resp:
                text = await resp.text()
                try:
                    return json.loads(text)
                except:
                    return text
        except Exception as e:
            log.warning("[soundbar] API %s %s failed: %s", method, path, e)
            return {}

    async def _cmd(self, capability: str, command: str, *args):
        """Execute a command via /devices/{id}/commands endpoint (the working way)."""
        payload = {"commands": [{"component": "main", "capability": capability, "command": command, "arguments": list(args)}]}
        result = await self._api("POST", f"/devices/{self._device_id}/commands", payload)
        if isinstance(result, dict):
            if "error" in result:
                return result.get("error", {}).get("code", "ERROR")
            return result.get("results", [{}])[0].get("status", "")
        return str(result)

    async def _sam_read(self, href: str) -> dict:
        """Read Samsung Audio API resource: trigger execute + poll status.
        Returns {} if rate limited (does NOT retry, to avoid worsening the limit)."""
        result = await self._cmd("execute", "execute", href)
        if result in ("", "RATE_LIMITED", "COMPLETED"):
            await asyncio.sleep(0.3)
            for _ in range(5):
                status = await self._api("GET", f"/devices/{self._device_id}/components/main/capabilities/execute/status")
                if isinstance(status, dict) and status.get("error", {}).get("code") == "TooManyRequestError":
                    return {}  # Don't retry, just return empty
                val = status.get("data", {}).get("value")
                if val and isinstance(val, dict):
                    return val.get("payload", {})
                await asyncio.sleep(0.2)
        return {}

    async def _sam_write(self, href: str, prop: str, value):
        """Write Samsung Audio API property using two-argument format: [href, {prop: value}]."""
        payload = {"commands": [{"component": "main", "capability": "execute", "command": "execute", "arguments": [href, {prop: value}]}]}
        result = await self._api("POST", f"/devices/{self._device_id}/commands", payload)
        if isinstance(result, dict):
            if "error" in result:
                return result.get("error", {}).get("code", "ERROR")
            return result.get("results", [{}])[0].get("status", "")
        return str(result)

    # -------- Update --------

    async def update(self):
        """Poll device status from SmartThings."""
        data = await self._api("GET", f"/devices/{self._device_id}/status")
        if "components" not in data:
            log.warning("[soundbar] Device status returned: %s", data)
            return

        comp = data["components"].get("main", {})

        switch = comp.get("switch", {})
        self._state = "playing" if switch.get("switch", {}).get("value") == "on" else "off"

        volume = comp.get("audioVolume", {})
        raw_volume = volume.get("volume", {}).get("value", 0)
        if time.monotonic() >= self._volume_hold_until or raw_volume == self._volume:
            self._volume = raw_volume
            self._volume_hold_until = 0.0

        raw_muted = comp.get("audioMute", {}).get("mute", {}).get("value") == "muted"
        if time.monotonic() >= self._mute_hold_until or raw_muted == self._muted:
            self._muted = raw_muted
            self._mute_hold_until = 0.0

        audio = comp.get("samsungvd.audioInputSource", {})
        self._input_source = audio.get("inputSource", {}).get("value", "digital")
        self._supported_input_sources = audio.get("supportedInputSources", {}).get("value", self._supported_input_sources)

        track = comp.get("audioTrackData", {})
        track_data = track.get("audioTrackData", {}).get("value", {})
        self._media_artist = track_data.get("artist", "")
        self._media_title = track_data.get("title", "")
        if self._media_title and self._media_title != self._old_media_title:
            self._old_media_title = self._media_title
            self._media_cover_url_update_time = datetime.datetime.now()
            self._media_cover_url = await self._fetch_artwork(self._media_artist, self._media_title)

        ocf = comp.get("ocf", {})
        self._manufacturer = ocf.get("ocf.manufacturerName", {}).get("value", "Samsung")
        self._model = ocf.get("ocf.modelNumber", {}).get("value", "HW-S60B")
        self._firmware_version = ocf.get("ocf.firmwareVersion", {}).get("value", "unknown")

        # Do not poll Samsung advanced-audio resources during the normal media
        # player update cycle. Switch/select/number entities use throttled
        # resource-specific refresh methods below.

    async def refresh_advanced_audio(self, min_interval: int = 300):
        """Refresh Night Mode / Bass Boost / Voice Enhancement, throttled.

        One refresh costs two SmartThings requests (execute + status). Multiple
        HA switch entities share this cache so their update cycles do not multiply
        API traffic.
        """
        now = time.monotonic()
        if now - self._advanced_audio_last_refresh < min_interval:
            return
        async with self._advanced_audio_lock:
            now = time.monotonic()
            if now - self._advanced_audio_last_refresh < min_interval:
                return
            self._advanced_audio_last_refresh = now
            payload = await self._sam_read("/sec/networkaudio/advancedaudio")
            if "x.com.samsung.networkaudio.nightmode" in payload:
                self._night_mode = payload["x.com.samsung.networkaudio.nightmode"]
                self._bass_mode = payload.get("x.com.samsung.networkaudio.bassboost", self._bass_mode)
                self._voice_amplifier = payload.get("x.com.samsung.networkaudio.voiceamplifier", self._voice_amplifier)

    async def refresh_soundmode(self, min_interval: int = 300):
        """Refresh sound mode, throttled."""
        now = time.monotonic()
        if now - self._soundmode_last_refresh < min_interval:
            return
        async with self._soundmode_lock:
            now = time.monotonic()
            if now - self._soundmode_last_refresh < min_interval:
                return
            self._soundmode_last_refresh = now
            payload = await self._sam_read("/sec/networkaudio/soundmode")
            if "x.com.samsung.networkaudio.soundmode" in payload:
                self._sound_mode = payload["x.com.samsung.networkaudio.soundmode"]
                self._supported_soundmodes = payload.get("x.com.samsung.networkaudio.supportedSoundmode", self._supported_soundmodes)

    async def refresh_woofer(self, min_interval: int = 300):
        """Refresh woofer level, throttled."""
        now = time.monotonic()
        if now - self._woofer_last_refresh < min_interval:
            return
        async with self._woofer_lock:
            now = time.monotonic()
            if now - self._woofer_last_refresh < min_interval:
                return
            self._woofer_last_refresh = now
            payload = await self._sam_read("/sec/networkaudio/woofer")
            if "x.com.samsung.networkaudio.woofer" in payload:
                self._woofer_level = payload["x.com.samsung.networkaudio.woofer"]
                self._woofer_connection = payload.get("x.com.samsung.networkaudio.connection", self._woofer_connection)

    async def _fetch_artwork(self, artist: str, title: str) -> str:
        if not artist or not title:
            return ""
        query = quote(f"{artist} {title}")
        try:
            async with self._session.get(f"https://itunes.apple.com/search?term={query}&media=music&entity=musicTrack&limit=1") as resp:
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
    def state(self) -> str: return self._state
    @property
    def volume_level(self) -> float: return min(self._volume / self._max_volume, 1.0)
    @property
    def volume_muted(self) -> bool: return self._muted
    @property
    def input_source(self): return self._input_source
    @property
    def supported_input_sources(self): return self._supported_input_sources
    @property
    def sound_mode(self): return self._sound_mode
    @property
    def supported_soundmodes(self): return self._supported_soundmodes
    @property
    def night_mode(self) -> bool | None:
        if self._night_mode is None:
            return None
        return self._night_mode == 1
    @property
    def bass_mode(self) -> bool | None:
        if self._bass_mode is None:
            return None
        return self._bass_mode == 1
    @property
    def voice_amplifier(self) -> bool | None:
        if self._voice_amplifier is None:
            return None
        return self._voice_amplifier == 1
    @property
    def woofer_level(self) -> int: return self._woofer_level
    @property
    def woofer_connection(self) -> str: return self._woofer_connection
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

    # -------- Commands --------

    async def set_volume(self, volume: float):
        level = max(0, min(self._max_volume, int(round(volume * self._max_volume))))
        previous = self._volume
        self._volume = level
        self._volume_hold_until = time.monotonic() + 20
        result = await self._cmd("audioVolume", "setVolume", level)
        if str(result).endswith("Error"):
            self._volume = previous
            self._volume_hold_until = 0.0
        return result

    async def mute_volume(self, mute: bool):
        previous = self._muted
        self._muted = mute
        self._mute_hold_until = time.monotonic() + 20
        result = await self._cmd("audioMute", "mute" if mute else "unmute")
        if str(result).endswith("Error"):
            self._muted = previous
            self._mute_hold_until = 0.0
        return result

    async def volume_up(self):
        level = max(0, min(self._max_volume, int(self._volume) + 1))
        return await self.set_volume(level / self._max_volume)

    async def volume_down(self):
        level = max(0, min(self._max_volume, int(self._volume) - 1))
        return await self.set_volume(level / self._max_volume)

    async def switch_off(self):
        await self._cmd("switch", "off")

    async def switch_on(self):
        await self._cmd("switch", "on")

    async def select_source(self, source: str):
        log.warning("[soundbar] Input source switching is blocked by firmware")

    async def select_sound_mode(self, sound_mode: str):
        await self._sam_write("/sec/networkaudio/soundmode", "x.com.samsung.networkaudio.soundmode", sound_mode)
        self._sound_mode = sound_mode

    async def set_night_mode(self, value: bool):
        await self._sam_write("/sec/networkaudio/advancedaudio", "x.com.samsung.networkaudio.nightmode", 1 if value else 0)
        self._night_mode = 1 if value else 0

    async def set_bass_mode(self, value: bool):
        await self._sam_write("/sec/networkaudio/advancedaudio", "x.com.samsung.networkaudio.bassboost", 1 if value else 0)
        self._bass_mode = 1 if value else 0

    async def set_voice_amplifier(self, value: bool):
        await self._sam_write("/sec/networkaudio/advancedaudio", "x.com.samsung.networkaudio.voiceamplifier", 1 if value else 0)
        self._voice_amplifier = 1 if value else 0

    async def set_woofer(self, level: int):
        await self._sam_write("/sec/networkaudio/woofer", "x.com.samsung.networkaudio.woofer", level)
        self._woofer_level = level

    async def media_play(self):
        await self._cmd("mediaPlayback", "play")

    async def media_pause(self):
        await self._cmd("mediaPlayback", "pause")

    async def media_stop(self):
        await self._cmd("mediaPlayback", "stop")

    async def media_next_track(self):
        await self._cmd("mediaPlayback", "fastForward")

    async def media_previous_track(self):
        await self._cmd("mediaPlayback", "rewind")
