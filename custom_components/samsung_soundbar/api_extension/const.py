from enum import Enum

class SpeakerIdentifier(Enum):
    FRONT_LEFT = "frontLeft"
    FRONT_RIGHT = "frontRight"
    SURROUND_LEFT = "surroundLeft"
    SURROUND_RIGHT = "surroundRight"
    CENTER = "center"
    SUBWOOFER = "subwoofer"

class RearSpeakerMode(Enum):
    OFF = "off"
    REAR_ONLY = "rear"
    FRONT_REAR = "surround"
