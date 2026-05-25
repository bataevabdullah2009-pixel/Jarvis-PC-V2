from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings


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
        model_exists = Path(self.settings.piper_model_path).exists()
        return VoiceProviderStatus(
            name=self.name,
            enabled=self.settings.piper_enabled,
            available=self.settings.piper_enabled and model_exists,
            details={"model_exists": model_exists},
        )


class XTTSLocalProvider:
    name = "xtts_local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> VoiceProviderStatus:
        model_exists = Path(self.settings.xtts_model_path).exists()
        return VoiceProviderStatus(
            name=self.name,
            enabled=self.settings.xtts_enabled,
            available=self.settings.xtts_enabled and model_exists,
            details={"model_exists": model_exists},
        )


class GPTSoVITSLocalProvider:
    name = "gpt_sovits_local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> VoiceProviderStatus:
        return VoiceProviderStatus(
            name=self.name,
            enabled=self.settings.gpt_sovits_enabled,
            available=False,
            details={"api_url": self.settings.gpt_sovits_api_url},
        )
