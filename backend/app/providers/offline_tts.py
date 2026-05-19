from __future__ import annotations

import importlib.util
from typing import Any


class OfflineTTS:
    provider = "pyttsx3"

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
            import pyttsx3

            engine = pyttsx3.init()
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
