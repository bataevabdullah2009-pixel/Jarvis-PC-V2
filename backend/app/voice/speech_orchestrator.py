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


def play_audio_background(audio_bytes: bytes, audio_format: str) -> None:
    """Plays audio bytes in a background daemon thread based on format (wav or mp3)."""
    logger = _speech_logger()
    logger.info("[PLAYBACK] Requesting audio: format=%s, bytes=%s", audio_format, len(audio_bytes))

    stop_all_audio()

    def _play_worker():
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
                    import pygame
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

    threading.Thread(target=_play_worker, daemon=True).start()


def _normalize(result: dict[str, Any], text: str, provider: str) -> dict[str, Any]:
    status = str(result.get("status") or "unknown")
    played = bool(result.get("played", result.get("spoken", False)))
    spoken = bool(result.get("spoken", played))
    audio_available = bool(result.get("audio_available", "audio" in result or status in {"completed", "dry_run"}))
    ok = bool(result.get("ok", spoken or status in {"completed", "dry_run"}))
    return {
        "requested": True,
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

    def available_providers(self) -> list[str]:
        providers = []
        if self.fish.available():
            providers.append("fish_audio")
        if self.resemble.available():
            providers.append("resemble")
        if self.edge.available():
            providers.append("edge_tts")
        if self.offline.available():
            providers.append("pyttsx3")
        return providers

    def say(self, text: str, *, dry_run: bool = False) -> dict[str, Any]:
        global _LAST_TTS_ERROR, _LAST_PROVIDER_USED
        logger = _speech_logger()

        safe_text = (text or "").strip() or "Сэр, слушаю вас."
        safe_text = safe_text[:500]

        started = time.perf_counter()
        primary = self.settings.tts_primary or "fish_audio"

        logger.info("[SPEECH] Primary TTS requested: %s", primary)

        # Attempt primary provider
        primary_result = None
        try:
            primary_result = self._try_provider(primary, safe_text, dry_run)
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

        primary_fix = None
        if primary == "fish_audio":
            if not self.settings.fish_audio_api_key or not self.settings.fish_audio_voice_id:
                primary_fix = "Основной голос Fish Audio недоступен: отсутствует JARVIS_FISH_AUDIO_API_KEY или JARVIS_FISH_AUDIO_VOICE_ID в .env."
            else:
                primary_fix = f"Основной голос Fish Audio недоступен. Ошибка: {last_error}. Проверьте лимиты/интернет."
        else:
            primary_fix = f"Основной голос {primary} недоступен. Ошибка: {last_error}."

        # If tts_require_fish_audio is True, we must NOT use any fallbacks other than text_only!
        if self.settings.tts_require_fish_audio:
            logger.info("[SPEECH] tts_require_fish_audio is True. Skipping non-Fish fallbacks.")
            return self._text_only(safe_text, f"Primary voice {primary} failed and other voice providers are disallowed by tts_require_fish_audio", started, primary_fix)

        if not self.settings.tts_fallback_enabled:
            logger.info("[SPEECH] Fallback disabled. Returning primary failure.")
            res = primary_result or self._text_only(safe_text, str(last_error), started, primary_fix)
            if "fix" not in res or not res["fix"]:
                res["fix"] = primary_fix
            return res

        # Fallback list priority order
        fallbacks = ["fish_audio", "resemble", "edge_tts", "pyttsx3"]
        for fallback in fallbacks:
            if fallback == primary:
                continue  # Already tried as primary

            logger.info("[SPEECH] Attempting fallback provider: %s", fallback)
            fallback_result = None
            try:
                fallback_result = self._try_provider(fallback, safe_text, dry_run)
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
        return self._text_only(safe_text, "All TTS providers failed.", started, primary_fix)

    def _try_provider(self, provider: str, text: str, dry_run: bool) -> dict[str, Any] | None:
        logger = _speech_logger()
        if provider == "fish_audio":
            if not self.fish.available():
                return None
            if dry_run:
                return _normalize({"ok": True, "status": "dry_run"}, text, "fish_audio")
            synth = self.fish.synthesize(text)
            if synth["ok"]:
                play_audio_background(synth["audio"], synth["format"])
                return _normalize({**synth, "spoken": True, "played": True}, text, "fish_audio")
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
        result = _normalize(text_only_response(text), text, "text_only")
        result["error"] = error
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["fix"] = fix or "Все голосовые движки (Fish Audio, Edge TTS, pyttsx3) недоступны. Проверьте .env или установите pyttsx3 через pip."
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
        return {
            "primary": self.settings.tts_primary,
            "primary_ready": (
                self.fish.available() if self.settings.tts_primary == "fish_audio"
                else self.edge.available() if self.settings.tts_primary == "edge_tts"
                else self.offline.available() if self.settings.tts_primary == "pyttsx3"
                else False
            ),
            "fallback": self.settings.tts_fallback,
            "fallback_enabled": self.settings.tts_fallback_enabled,
            "available_providers": self.available_providers(),
            "last_provider_used": _LAST_PROVIDER_USED,
            "last_error": _LAST_TTS_ERROR,
        }
