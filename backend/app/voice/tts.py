from __future__ import annotations

from logging.handlers import RotatingFileHandler
from typing import Any
import logging
import time

from app.core.config import LOG_DIR, Settings
from app.providers.fish_audio import FishAudioTTS
from app.providers.offline_tts import OfflineTTS, text_only_response


_LAST_TTS_ERROR: str | None = None
_LAST_PROVIDER_USED: str | None = None


def _tts_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("jarvis.tts")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "").endswith("tts.log") for handler in logger.handlers):
        handler = RotatingFileHandler(LOG_DIR / "tts.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    return logger


def _normalize(result: dict[str, Any], text: str) -> dict[str, Any]:
    provider = str(result.get("provider") or result.get("mode") or "text_only")
    status = str(result.get("status") or "unknown")
    played = bool(result.get("played", result.get("spoken", False)))
    spoken = bool(result.get("spoken", played))
    audio_available = bool(result.get("audio_available", spoken or status in {"completed", "dry_run"}))
    ok = bool(result.get("ok", spoken or status in {"completed", "dry_run"}))
    return {
        **result,
        "requested": bool(result.get("requested", True)),
        "ok": ok,
        "provider": provider,
        "spoken": spoken,
        "played": played,
        "audio_available": audio_available,
        "fallback_used": bool(result.get("fallback_used", False)),
        "error": None if ok else result.get("error") or "TTS provider unavailable",
        "text": result.get("text") or text,
    }


class TTSService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fish = FishAudioTTS(settings)
        self.offline = OfflineTTS()

    def speak(self, text: str, *, dry_run: bool = False) -> dict[str, Any]:
        global _LAST_TTS_ERROR, _LAST_PROVIDER_USED

        safe_text = (text or "").strip() or "Команда выполнена."
        safe_text = safe_text[:500]
        logger = _tts_logger()
        started = time.perf_counter()
        logger.info("[TTS] provider=%s", self.settings.tts_primary)
        logger.info("[TTS] fallback_enabled=%s require_fish_audio=%s", self.settings.tts_fallback_enabled, self.settings.tts_require_fish_audio)
        logger.info("[TTS] key_present=%s", bool(self.settings.fish_audio_api_key))
        logger.info("[TTS] voice_id_present=%s", bool(self.settings.fish_audio_voice_id))
        logger.info("[TTS] request started")

        if self.settings.tts_primary != "fish_audio":
            message = f"Unsupported primary TTS provider: {self.settings.tts_primary}"
            _LAST_TTS_ERROR = message
            _LAST_PROVIDER_USED = self.settings.tts_primary
            logger.info("[TTS] error=%s", message)
            return self._text_only(safe_text, message, started)

        fish_result = _normalize(self.fish.speak(safe_text, dry_run=dry_run), safe_text)
        _LAST_PROVIDER_USED = "fish_audio"
        logger.info("[TTS] provider=fish_audio")
        logger.info("[TTS] status_code=%s", fish_result.get("status_code"))
        logger.info("[TTS] status=%s", fish_result.get("status"))
        logger.info("[TTS] audio_bytes=%s", fish_result.get("audio_bytes"))
        logger.info("[TTS] error_type=%s", fish_result.get("error_type"))
        logger.info("[TTS] retry_count=%s", fish_result.get("retry_count"))
        logger.info("[TTS] fallback_used=false")

        if fish_result["ok"]:
            _LAST_TTS_ERROR = None
            fish_result["latency_ms"] = fish_result.get("latency_ms") or int((time.perf_counter() - started) * 1000)
            return fish_result

        _LAST_TTS_ERROR = str(fish_result.get("error") or fish_result.get("status"))
        logger.info("[TTS] error=%s", _LAST_TTS_ERROR)

        if self.settings.tts_require_fish_audio or not self.settings.tts_fallback_enabled:
            logger.info("[TTS] fallback_used=false reason=fish_required_or_fallback_disabled")
            return {
                **fish_result,
                "ok": False,
                "provider": "fish_audio",
                "called": True,
                "played": False,
                "spoken": False,
                "fallback_used": False,
                "warning": f"Fish Audio недоступен: {_LAST_TTS_ERROR}",
                "latency_ms": fish_result.get("latency_ms") or int((time.perf_counter() - started) * 1000),
            }

        logger.info("[TTS] fallback_used=true provider=pyttsx3")
        offline_result = _normalize(self.offline.speak(safe_text, dry_run=dry_run), safe_text)
        offline_result["fallback_from"] = fish_result
        offline_result["fallback_used"] = True
        offline_result["warning"] = "Использован системный голос, Fish Audio недоступен."
        _LAST_PROVIDER_USED = "pyttsx3"
        if offline_result["ok"]:
            _LAST_TTS_ERROR = None
            return offline_result

        _LAST_TTS_ERROR = str(offline_result.get("error") or offline_result.get("status"))
        logger.info("[TTS] fallback_error=%s", _LAST_TTS_ERROR)
        return self._text_only(safe_text, _LAST_TTS_ERROR, started, fallback_from=[fish_result, offline_result])

    def _text_only(
        self,
        text: str,
        error: str,
        started: float,
        *,
        fallback_from: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result = _normalize(text_only_response(text), text)
        result["error"] = error
        result["fallback_used"] = False
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        if fallback_from:
            result["fallback_from"] = fallback_from
        return result

    def status(self) -> dict[str, Any]:
        return {
            "primary": self.settings.tts_primary,
            "primary_ready": self.fish.available(),
            "fallback": self.settings.tts_fallback,
            "fallback_enabled": self.settings.tts_fallback_enabled,
            "fallback_ready": self.offline.available() if self.settings.tts_fallback_enabled else False,
            "system_audio_ready": self.offline.available(),
            "require_fish_audio": self.settings.tts_require_fish_audio,
            "last_provider_used": _LAST_PROVIDER_USED,
            "last_error": _LAST_TTS_ERROR,
        }
