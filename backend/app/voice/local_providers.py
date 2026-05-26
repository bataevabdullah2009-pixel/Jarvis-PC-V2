from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.providers.gpt_sovits_local import GPTSoVITSLocalTTS
from app.providers.piper_local import PiperLocalTTS


@dataclass(slots=True)
class VoiceProviderStatus:
    name: str
    enabled: bool
    available: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "available": self.available, **self.details}


class PiperLocalProvider:
    name = "piper_local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> VoiceProviderStatus:
        status = PiperLocalTTS(self.settings).status()
        return VoiceProviderStatus(
            name=self.name,
            enabled=bool(status.get("enabled")),
            available=bool(status.get("available")),
            details={key: value for key, value in status.items() if key not in {"enabled", "available"}},
        )


class XTTSLocalProvider:
    name = "xtts_local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> VoiceProviderStatus:
        return VoiceProviderStatus(
            name=self.name,
            enabled=self.settings.xtts_enabled,
            available=False,
            details={"api_url": self.settings.xtts_api_url},
        )


class GPTSoVITSLocalProvider:
    name = "gpt_sovits_local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> VoiceProviderStatus:
        status = GPTSoVITSLocalTTS(self.settings).status()
        return VoiceProviderStatus(
            name=self.name,
            enabled=bool(status.get("enabled")),
            available=bool(status.get("available")),
            details={key: value for key, value in status.items() if key not in {"enabled", "available"}},
        )


class RVCConverterProvider:
    name = "rvc_converter"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> VoiceProviderStatus:
        return VoiceProviderStatus(
            name=self.name,
            enabled=self.settings.rvc_enabled,
            available=False,
            details={"api_url": self.settings.rvc_api_url},
        )
