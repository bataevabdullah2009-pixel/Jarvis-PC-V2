from __future__ import annotations

import importlib.util
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings


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
            if self.settings:
                # scale voice_volume from 0-100 to 0.0-1.0
                volume = max(0.0, min(1.0, self.settings.voice_volume / 100.0))
                engine.setProperty("volume", volume)
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
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
