from __future__ import annotations

from typing import Any
from app.core.config import Settings
from app.voice.speech_orchestrator import SpeechOrchestrator


class TTSService(SpeechOrchestrator):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    def speak(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Backwards-compatibility method mapping speak to say."""
        if blocking:
            return self.say(text, dry_run=dry_run, blocking=blocking)
        return self.say(text, dry_run=dry_run)
