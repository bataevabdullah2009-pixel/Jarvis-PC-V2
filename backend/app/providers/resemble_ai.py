from __future__ import annotations
from typing import Any
from app.core.config import Settings

class ResembleTTS:
    provider = "resemble"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        # User requested not to use Resemble AI, keep as disabled stub
        return False

    def speak(self, text: str, *, dry_run: bool = False) -> dict[str, Any]:
        return {
            "mode": "resemble",
            "provider": self.provider,
            "spoken": False,
            "ok": False,
            "audio_available": False,
            "status": "not_configured",
            "error": "resemble_not_configured",
            "text": text,
        }
