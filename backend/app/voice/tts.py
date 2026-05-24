from __future__ import annotations

from typing import Any
from app.core.config import Settings
from app.voice.speech_orchestrator import SpeechOrchestrator


class TTSService(SpeechOrchestrator):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    def speak(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Backwards-compatibility method mapping speak to say."""
        from app.voice import anti_echo
        anti_echo.mark_tts_started(text)
        try:
            if blocking:
                res = self.say(text, dry_run=dry_run, blocking=blocking)
            else:
                res = self.say(text, dry_run=dry_run)
            
            if res.get("ok"):
                anti_echo.mark_tts_completed(text)
            else:
                anti_echo.mark_tts_failed(text, str(res.get("error", "TTS provider failure")))
            return res
        except Exception as e:
            anti_echo.mark_tts_failed(text, str(e))
            raise
