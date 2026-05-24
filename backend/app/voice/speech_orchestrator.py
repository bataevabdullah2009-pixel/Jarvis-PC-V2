from __future__ import annotations

import os
import tempfile
import time
import struct
import threading
import logging
from logging.handlers import RotatingFileHandler
from typing import Any
import winsound

from app.core.config import LOG_DIR, Settings
from app.providers.fish_audio import FishAudioTTS
from app.providers.resemble_ai import ResembleTTS
from app.providers.edge_tts_provider import EdgeTTSProvider
from app.providers.offline_tts import OfflineTTS, text_only_response

_PLAYBACK_LOCK = threading.Lock()
_LAST_TTS_ERROR: str | None = None
_LAST_PROVIDER_USED: str | None = None


def _speech_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("jarvis.speech")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "").endswith("speech.log")
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(LOG_DIR / "speech.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    return logger


def stop_all_audio() -> None:
    """Stops both winsound and pygame mixer playback cleanly."""
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
    except Exception:
        pass


def play_audio_sync(audio_bytes: bytes, audio_format: str) -> None:
    """Plays audio bytes synchronously based on format (wav or mp3)."""
    logger = _speech_logger()
    logger.info("[PLAYBACK] Requesting audio sync: format=%s, bytes=%s", audio_format, len(audio_bytes))

    stop_all_audio()

    with _PLAYBACK_LOCK:
        if audio_format.lower() == "wav":
            patched_audio = audio_bytes
            if len(audio_bytes) >= 44:
                try:
                    riff, file_size, wave = struct.unpack("<4sI4s", audio_bytes[:12])
                    if riff == b"RIFF" and wave == b"WAVE":
                        offset = 12
                        data_chunk_offset = -1
                        while offset < len(audio_bytes) - 8:
                            chunk_id, chunk_size = struct.unpack("<4sI", audio_bytes[offset:offset+8])
                            if chunk_id == b"data":
                                data_chunk_offset = offset
                                break
                            if chunk_size < 0 or offset + 8 + chunk_size > len(audio_bytes):
                                break
                            offset += 8 + chunk_size

                        if data_chunk_offset != -1:
                            patched_data = bytearray(audio_bytes)
                            struct.pack_into("<I", patched_data, 4, len(audio_bytes) - 8)
                            struct.pack_into("<I", patched_data, data_chunk_offset + 4, len(audio_bytes) - (data_chunk_offset + 8))
                            patched_audio = bytes(patched_data)
                except Exception as e:
                    logger.error("[PLAYBACK] WAV patching error: %s", e)

            try:
                winsound.PlaySound(patched_audio, winsound.SND_MEMORY)
            except Exception as e:
                logger.error("[PLAYBACK] winsound error: %s", e)

        elif audio_format.lower() == "mp3":
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
            except Exception as e:
                logger.error("[PLAYBACK] pygame.mixer.init error: %s", e)
                return

            temp_path = None
            try:
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, f"jarvis_speech_{int(time.time()*1000)}.mp3")
                with open(temp_path, "wb") as f:
                    f.write(audio_bytes)

                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
            except Exception as e:
                logger.error("[PLAYBACK] pygame play error: %s", e)
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        logger.info("[PLAYBACK] Safely deleted temp audio file: %s", temp_path)
                    except Exception as e:
                        logger.error("[PLAYBACK] Failed to delete temp audio file %s: %s", temp_path, e)
        else:
            logger.error("[PLAYBACK] Unsupported audio format: %s", audio_format)


def play_audio_background(audio_bytes: bytes, audio_format: str) -> None:
    """Plays audio bytes in a background daemon thread based on format (wav or mp3)."""
    threading.Thread(target=play_audio_sync, args=(audio_bytes, audio_format), daemon=True).start()


def _normalize(result: dict[str, Any], text: str, provider: str) -> dict[str, Any]:
    status = str(result.get("status") or "unknown")
    played = bool(result.get("played", result.get("spoken", False)))
    spoken = bool(result.get("spoken", played))
    audio_available = bool(result.get("audio_available", "audio" in result or status in {"completed", "dry_run"}))
    ok = bool(result.get("ok", spoken or status in {"completed", "dry_run"}))
    return {
        "requested": True,
        "called": bool(result.get("called", ok or provider != "text_only")),
        "ok": ok,
        "provider": provider,
        "mode": provider,
        "spoken": spoken,
        "played": played,
        "audio_available": audio_available,
        "fallback_used": bool(result.get("fallback_used", False)),
        "error": None if ok else result.get("error") or result.get("error_message") or "TTS provider unavailable",
        "text": result.get("text") or text,
        "status": status,
        "latency_ms": result.get("latency_ms", 0),
        "audio_bytes": result.get("audio_bytes", len(result.get("audio", b"")) if "audio" in result else 0),
        "format": result.get("format", "mp3" if provider == "edge_tts" else "wav"),
        "audio": result.get("audio"),
    }



class SpeechOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fish = FishAudioTTS(settings)
        self.resemble = ResembleTTS(settings)
        self.edge = EdgeTTSProvider(settings)
        self.offline = OfflineTTS(settings)

    def _fish_required(self) -> bool:
        return bool(
            self.settings.tts_require_fish_audio
            or self.settings.voice_profile.strip().lower() == "jarvis style"
        )

    def available_providers(self) -> list[str]:
        providers = []
        if self.fish.available():
            providers.append("fish_audio")
        if self._fish_required() or not self.settings.tts_fallback_enabled:
            return providers
        if self.resemble.available():
            providers.append("resemble")
        if self.edge.available():
            providers.append("edge_tts")
        if self.offline.available():
            providers.append("pyttsx3")
        return providers

    def say(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
        global _LAST_TTS_ERROR, _LAST_PROVIDER_USED
        logger = _speech_logger()

        safe_text = (text or "").strip() or "Сэр, слушаю вас."
        safe_text = safe_text[:500]

        started = time.perf_counter()
        voice_locked = self._fish_required()
        primary = "fish_audio" if voice_locked else (self.settings.tts_primary or "fish_audio")

        logger.info("[SPEECH] Primary TTS requested: %s", primary)

        # Pre-check Fish Audio configuration
        fish_configured = bool(self.settings.fish_audio_api_key and self.settings.fish_audio_voice_id)
        fish_error_type = None
        if primary == "fish_audio" and not fish_configured:
            fish_error_type = "fish_key_missing" if not self.settings.fish_audio_api_key else "fish_voice_id_missing"
            primary_fix = "Добавьте JARVIS_FISH_AUDIO_API_KEY и JARVIS_FISH_AUDIO_VOICE_ID в .env"
        else:
            primary_fix = None

        # Attempt primary provider if available
        primary_result = None
        if primary == "fish_audio" and not fish_configured:
            last_error = "Fish Audio is not configured: " + ("API key is missing" if fish_error_type == "fish_key_missing" else "Voice ID is missing")
            primary_result = {"ok": False, "error": last_error, "status": "failed", "error_type": fish_error_type, "fix": primary_fix}
        else:
            try:
                primary_result = self._try_provider(primary, safe_text, dry_run, blocking=blocking)
            except Exception as e:
                logger.exception("[SPEECH] Primary provider %s raised an exception: %s", primary, e)
                primary_result = {"ok": False, "error": str(e), "status": "failed"}

        if primary_result and primary_result["ok"]:
            _LAST_TTS_ERROR = None
            _LAST_PROVIDER_USED = primary
            primary_result["latency_ms"] = primary_result.get("latency_ms") or int((time.perf_counter() - started) * 1000)
            logger.info("[SPEECH] Primary provider %s succeeded in %sms", primary, primary_result["latency_ms"])
            return primary_result

        # Handle failure/fallback
        last_error = primary_result.get("error") if primary_result else f"Provider {primary} not available"
        _LAST_TTS_ERROR = str(last_error)
        logger.warning("[SPEECH] Primary provider %s failed: %s", primary, last_error)

        if not primary_fix:
            if primary == "fish_audio":
                primary_fix = "Добавьте JARVIS_FISH_AUDIO_API_KEY и JARVIS_FISH_AUDIO_VOICE_ID в .env"
                if not self.settings.fish_audio_api_key:
                    fish_error_type = "fish_key_missing"
                elif not self.settings.fish_audio_voice_id:
                    fish_error_type = "fish_voice_id_missing"
                else:
                    fish_error_type = "fish_audio_unavailable"
            else:
                primary_fix = f"Основной голос {primary} недоступен. Ошибка: {last_error}."

        # If tts_require_fish_audio is True, we must NOT use any fallbacks other than text_only!
        if voice_locked:
            logger.info("[SPEECH] tts_require_fish_audio is True. Skipping non-Fish fallbacks.")
            res = self._text_only(safe_text, f"Primary voice {primary} failed and other voice providers are disallowed by tts_require_fish_audio", started, primary_fix)
            res["provider"] = "text_only"
            res["error_type"] = fish_error_type or "fish_audio_unavailable"
            res["fallback_used"] = False
            return res

        if not self.settings.tts_fallback_enabled:
            logger.info("[SPEECH] Fallback disabled. Returning primary failure.")
            res = self._text_only(safe_text, str(last_error), started, primary_fix)
            res["provider"] = "text_only"
            if fish_error_type:
                res["error_type"] = fish_error_type
            return res

        # Fallback list priority order
        fallbacks = ["fish_audio", "resemble", "edge_tts", "pyttsx3"]
        for fallback in fallbacks:
            if fallback == primary:
                continue  # Already tried as primary

            logger.info("[SPEECH] Attempting fallback provider: %s", fallback)
            fallback_result = None
            try:
                fallback_result = self._try_provider(fallback, safe_text, dry_run, blocking=blocking)
            except Exception as e:
                logger.exception("[SPEECH] Fallback provider %s raised an exception: %s", fallback, e)
                fallback_result = {"ok": False, "error": str(e), "status": "failed"}

            if fallback_result and fallback_result["ok"]:
                _LAST_TTS_ERROR = None
                _LAST_PROVIDER_USED = fallback
                fallback_result["fallback_used"] = True
                fallback_result["warning"] = f"Использован резервный голос ({fallback}), так как основной {primary} недоступен."
                fallback_result["latency_ms"] = int((time.perf_counter() - started) * 1000)
                fallback_result["fix"] = primary_fix
                logger.info("[SPEECH] Fallback provider %s succeeded in %sms", fallback, fallback_result["latency_ms"])
                return fallback_result

            if fallback_result:
                logger.warning("[SPEECH] Fallback provider %s failed: %s", fallback, fallback_result.get("error"))

        # Pure text only fallback
        logger.error("[SPEECH] All TTS providers failed. Returning text-only fallback.")
        _LAST_PROVIDER_USED = "text_only"
        res = self._text_only(safe_text, "All TTS providers failed.", started, primary_fix)
        res["provider"] = "text_only"
        if fish_error_type:
            res["error_type"] = fish_error_type
        return res

    def _try_provider(self, provider: str, text: str, dry_run: bool, blocking: bool = False) -> dict[str, Any] | None:
        logger = _speech_logger()
        if provider == "fish_audio":
            if not self.fish.available():
                return None
            if dry_run:
                return _normalize({"ok": True, "status": "dry_run"}, text, "fish_audio")
            synth = self.fish.synthesize(text)
            if synth["ok"]:
                if blocking:
                    play_audio_sync(synth["audio"], synth["format"])
                else:
                    play_audio_background(synth["audio"], synth["format"])
                return _normalize({**synth, "spoken": True, "played": True, "status": "completed"}, text, "fish_audio")
            return _normalize(synth, text, "fish_audio")

        elif provider == "resemble":
            if not self.resemble.available():
                return None
            synth = self.resemble.speak(text, dry_run=dry_run)
            return _normalize(synth, text, "resemble")

        elif provider == "edge_tts":
            if not self.edge.available():
                return None
            if dry_run:
                return _normalize({"ok": True, "status": "dry_run"}, text, "edge_tts")
            synth = self.edge.synthesize(text)
            if synth["ok"]:
                if blocking:
                    play_audio_sync(synth["audio"], synth["format"])
                else:
                    play_audio_background(synth["audio"], synth["format"])
                return _normalize({**synth, "spoken": True, "played": True}, text, "edge_tts")
            return _normalize(synth, text, "edge_tts")

        elif provider == "pyttsx3":
            if not self.offline.available():
                return None
            # pyttsx3 plays internally in its speak method
            res = self.offline.speak(text, dry_run=dry_run)
            return _normalize(res, text, "pyttsx3")

        return None

    def _text_only(self, text: str, error: str, started: float, fix: str | None = None) -> dict[str, Any]:
        global _LAST_PROVIDER_USED
        _LAST_PROVIDER_USED = "text_only"
        result = _normalize(text_only_response(text), text, "text_only")
        result["error"] = error
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["fix"] = fix or "Голос Джарвиса временно недоступен. Проверьте Fish Audio key / voice id / лимиты."
        return result

    def say_greeting(self, text: str) -> dict[str, Any]:
        return self.say(text)

    def say_success(self, action: str, text: str) -> dict[str, Any]:
        return self.say(text)

    def say_error(self, text: str) -> dict[str, Any]:
        return self.say(text)

    def say_action_start(self, text: str) -> dict[str, Any]:
        return self.say(text)

    def status(self) -> dict[str, Any]:
        voice_locked = self._fish_required()
        primary = "fish_audio" if voice_locked else (self.settings.tts_primary or "fish_audio")
        fallback_enabled = self.settings.tts_fallback_enabled and not voice_locked
        
        fallback_used = False
        if _LAST_PROVIDER_USED and _LAST_PROVIDER_USED != primary and _LAST_PROVIDER_USED != "text_only":
            fallback_used = True
            
        voice_identity = "text_only"
        if _LAST_PROVIDER_USED == "fish_audio":
            voice_identity = "jarvis"
        elif _LAST_PROVIDER_USED in {"resemble", "edge_tts", "pyttsx3"}:
            voice_identity = "fallback"

        return {
            "voice_locked": voice_locked,
            "primary": primary,
            "fallback_enabled": fallback_enabled,
            "fallback_used": fallback_used,
            "last_provider_used": _LAST_PROVIDER_USED or "none",
            "voice_identity": voice_identity,
            "primary_ready": (
                self.fish.available() if primary == "fish_audio"
                else self.edge.available() if primary == "edge_tts"
                else self.offline.available() if primary == "pyttsx3"
                else False
            ),
            "fallback": self.settings.tts_fallback,
            "available_providers": self.available_providers(),
            "last_error": _LAST_TTS_ERROR,
        }
