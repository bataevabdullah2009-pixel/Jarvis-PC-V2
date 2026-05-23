from __future__ import annotations

import importlib.util
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger("jarvis.offline_tts")
_STABLE_VOICE_ID: str | None = None


class OfflineTTS:
    provider = "pyttsx3"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def available(self) -> bool:
        return importlib.util.find_spec("pyttsx3") is not None

    def speak(self, text: str, *, dry_run: bool = False) -> dict[str, Any]:
        if not self.available():
            return {
                "mode": "offline_tts",
                "provider": self.provider,
                "spoken": False,
                "ok": False,
                "audio_available": False,
                "status": "not_installed",
                "error": "pyttsx3_not_installed",
                "text": text,
            }

        if dry_run:
            return {
                "mode": "offline_tts",
                "provider": self.provider,
                "spoken": False,
                "ok": True,
                "audio_available": True,
                "status": "dry_run",
                "text": text,
            }

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass

        try:
            import pyttsx3

            engine = pyttsx3.init()
            
            # Rate
            rate = 175
            if self.settings and hasattr(self.settings, "tts_pyttsx3_rate"):
                rate = self.settings.tts_pyttsx3_rate
            engine.setProperty("rate", rate)
            
            # Volume
            volume = 0.8
            if self.settings and hasattr(self.settings, "tts_pyttsx3_volume"):
                volume = self.settings.tts_pyttsx3_volume
            elif self.settings and hasattr(self.settings, "voice_volume"):
                volume = max(0.0, min(1.0, self.settings.voice_volume / 100.0))
            engine.setProperty("volume", volume)

            # Stable Voice ID logic
            voice_id = None
            if self.settings and hasattr(self.settings, "tts_pyttsx3_voice_id") and self.settings.tts_pyttsx3_voice_id:
                voice_id = self.settings.tts_pyttsx3_voice_id
            else:
                global _STABLE_VOICE_ID
                if _STABLE_VOICE_ID is None:
                    voices = engine.getProperty("voices")
                    if voices:
                        # Find a Russian voice first, otherwise use first available voice
                        ru_voice = None
                        for v in voices:
                            langs = getattr(v, "languages", [])
                            if langs and any("ru" in str(l).lower() for l in langs):
                                ru_voice = v.id
                                break
                            if "russian" in str(v.name).lower():
                                ru_voice = v.id
                                break
                        _STABLE_VOICE_ID = ru_voice or voices[0].id
                        logger.info("Selected stable offline pyttsx3 voice: %s", _STABLE_VOICE_ID)
                voice_id = _STABLE_VOICE_ID

            if voice_id:
                engine.setProperty("voice", voice_id)

            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            logger.exception("OfflineTTS pyttsx3 speak failed")
            return {
                "mode": "offline_tts",
                "provider": self.provider,
                "spoken": False,
                "ok": False,
                "audio_available": False,
                "status": "failed",
                "error": exc.__class__.__name__,
                "text": text,
            }
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

        return {
            "mode": "offline_tts",
            "provider": self.provider,
            "spoken": True,
            "ok": True,
            "audio_available": True,
            "status": "completed",
            "text": text,
        }


def text_only_response(text: str) -> dict[str, Any]:
    return {
        "mode": "text_only",
        "provider": "text_only",
        "spoken": False,
        "ok": False,
        "audio_available": False,
        "status": "text_only",
        "error": "TTS provider unavailable",
        "text": text,
    }
