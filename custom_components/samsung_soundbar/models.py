from dataclasses import dataclass

from .api_extension.SoundbarDevice import SoundbarDevice

@dataclass
class DeviceConfig:
    config: dict
    device: SoundbarDevice

@dataclass
class SoundbarConfig:
    api: None
    devices: dict
