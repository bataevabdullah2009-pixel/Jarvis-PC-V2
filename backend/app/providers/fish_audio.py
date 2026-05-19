from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import time
import winsound
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx

from app.core.config import LOG_DIR, Settings


CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 20.0
FISH_TOTAL_TIMEOUT_SECONDS = 25.0
MAX_RETRIES = 1
_AUDIO_CACHE: dict[str, dict[str, Any]] = {}
_CACHEABLE_TEXT_LENGTH = 500


def _provider_logger(name: str, filename: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "").endswith(filename)
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(LOG_DIR / filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    return logger


def _fish_logger() -> logging.Logger:
    return _provider_logger("jarvis.provider.fish_audio", "fish_audio.log")


def _provider_log() -> logging.Logger:
    return _provider_logger("jarvis.provider", "provider.log")


def _fix_for(status_code: int | None, error_type: str) -> str:
    if error_type == "env_missing":
        return "Backend did not load .env or Fish Audio key/voice id is missing."
    if status_code == 401:
        return "Fish Audio 401: invalid or revoked API key."
    if status_code == 403:
        return "Fish Audio 403: check API key permissions."
    if status_code == 404:
        return "Fish Audio 404: voice id or endpoint not found."
    if status_code == 429:
        return "Fish Audio 429: rate limit or quota exceeded."
    if status_code and status_code >= 500:
        return "Fish Audio server error, retry later."
    if error_type in {"ConnectTimeout", "ReadTimeout", "TimeoutException"}:
        return "Fish Audio SSL/network timeout: check network, proxy, DNS, or endpoint reachability."
    if error_type in {"ConnectError", "NetworkError", "TransportError"}:
        return "Fish Audio network error: check network, proxy, DNS, or TLS interception."
    if error_type == "playback_failed":
        return "Audio was received, but local playback failed."
    return "See logs/fish_audio.log and logs/tts.log."


class FishAudioTTS:
    endpoint = "https://api.fish.audio/v1/tts"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return bool(self.settings.fish_audio_api_key and self.settings.fish_audio_voice_id)

    def synthesize(self, text: str) -> dict[str, Any]:
        fish_logger = _fish_logger()
        provider_logger = _provider_log()
        safe_text = self._tts_text(text)

        if not self.available():
            fish_logger.info("[FISH] called=false endpoint=%s voice_id_present=%s reason=missing_key_or_voice", self.endpoint, bool(self.settings.fish_audio_voice_id))
            provider_logger.info("[FISH] called=false endpoint=%s voice_id_present=%s reason=missing_key_or_voice", self.endpoint, bool(self.settings.fish_audio_voice_id))
            fish_logger.info("[FISH] status_code=null latency_ms=0 error_type=env_missing error_message=missing_key_or_voice retry_count=0")
            provider_logger.info("[FISH] status_code=null audio_bytes=0 error_type=env_missing error_message=missing_key_or_voice retry_count=0")
            return {
                "ok": False,
                "provider": "fish_audio",
                "endpoint": self.endpoint,
                "called": False,
                "status_code": None,
                "error_type": "env_missing",
                "error_message": "Fish Audio key or voice id is missing.",
                "fix": _fix_for(None, "env_missing"),
                "retry_count": 0,
                "latency_ms": 0,
            }

        fish_logger.info(
            "[FISH] called=true endpoint=%s voice_id_present=%s connect_timeout=%s read_timeout=%s total_timeout=%s",
            self.endpoint,
            bool(self.settings.fish_audio_voice_id),
            CONNECT_TIMEOUT_SECONDS,
            READ_TIMEOUT_SECONDS,
            FISH_TOTAL_TIMEOUT_SECONDS,
        )
        provider_logger.info(
            "[FISH] called=true endpoint=%s voice_id_present=%s",
            self.endpoint,
            bool(self.settings.fish_audio_voice_id),
        )

        cache_key = self._cache_key(safe_text)
        if cache_key in _AUDIO_CACHE:
            cached = _AUDIO_CACHE[cache_key]
            fish_logger.info("[FISH] status_code=200 latency_ms=0 audio_bytes=%s cached=true retry_count=0", cached["audio_bytes"])
            return {**cached, "ok": True, "provider": "fish_audio", "endpoint": self.endpoint, "status_code": 200, "cached": True, "latency_ms": 0, "retry_count": 0}

        payload = {
            "text": safe_text,
            "reference_id": self.settings.fish_audio_voice_id,
            "temperature": 0.7,
            "top_p": 0.7,
            "format": "wav",
            "sample_rate": 44100,
            "normalize": True,
            "latency": "normal",
        }
        headers = {
            "Authorization": f"Bearer {self.settings.fish_audio_api_key}",
            "Content-Type": "application/json",
            "model": "s2-pro",
        }
        timeout = httpx.Timeout(
            FISH_TOTAL_TIMEOUT_SECONDS,
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=5.0,
            pool=5.0,
        )

        started = time.perf_counter()
        retry_count = 0
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            retry_count = attempt
            try:
                with httpx.Client(timeout=timeout, trust_env=True) as client:
                    response = client.post(self.endpoint, headers=headers, json=payload)
                latency_ms = int((time.perf_counter() - started) * 1000)
                status_code = response.status_code
                if status_code >= 400:
                    message = self._extract_error_message(response.text) or response.reason_phrase
                    self._log_failure(fish_logger, provider_logger, status_code, latency_ms, "HTTPStatusError", message, retry_count)
                    return self._failed_result(status_code, "HTTPStatusError", message, latency_ms, retry_count, safe_text)

                audio = response.content
                if not audio:
                    self._log_failure(fish_logger, provider_logger, status_code, latency_ms, "empty_audio", "Fish Audio returned empty audio payload.", retry_count)
                    return self._failed_result(status_code, "empty_audio", "Fish Audio returned empty audio payload.", latency_ms, retry_count, safe_text)

                content_type = response.headers.get("Content-Type", "")
                audio_format = "mp3" if "mpeg" in content_type.lower() else "wav"
                result = {
                    "ok": True,
                    "provider": "fish_audio",
                    "endpoint": self.endpoint,
                    "called": True,
                    "status_code": status_code,
                    "audio": audio,
                    "audio_bytes": len(audio),
                    "format": audio_format,
                    "latency_ms": latency_ms,
                    "retry_count": retry_count,
                }
                if len(safe_text) <= _CACHEABLE_TEXT_LENGTH:
                    _AUDIO_CACHE[cache_key] = {key: value for key, value in result.items() if key != "ok"}
                fish_logger.info(
                    "[FISH] status_code=%s latency_ms=%s audio_bytes=%s error_type=null error_message=null retry_count=%s",
                    status_code,
                    latency_ms,
                    len(audio),
                    retry_count,
                )
                provider_logger.info(
                    "[FISH] status_code=%s latency_ms=%s audio_bytes=%s error_type=null error_message=null retry_count=%s",
                    status_code,
                    latency_ms,
                    len(audio),
                    retry_count,
                )
                return result
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_error = exc
                latency_ms = int((time.perf_counter() - started) * 1000)
                message = str(exc) or exc.__class__.__name__
                self._log_failure(fish_logger, provider_logger, None, latency_ms, exc.__class__.__name__, message, retry_count)
                should_retry = isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)) and latency_ms < 10_000 and attempt < MAX_RETRIES
                if not should_retry:
                    break

        latency_ms = int((time.perf_counter() - started) * 1000)
        exc = last_error or RuntimeError("unknown_fish_audio_error")
        return self._failed_result(None, exc.__class__.__name__, str(exc) or exc.__class__.__name__, latency_ms, retry_count, safe_text)

    def speak(self, text: str, *, dry_run: bool = False) -> dict[str, Any]:
        safe_text = self._tts_text(text)
        if not self.available():
            return self._failed("not_configured", "Fish Audio key or voice id is missing.", None, 0, safe_text, error_type="env_missing", called=False)

        if dry_run:
            return {
                "mode": "fish_audio",
                "provider": "fish_audio",
                "requested": True,
                "called": False,
                "spoken": False,
                "played": False,
                "ok": True,
                "audio_available": True,
                "status": "dry_run",
                "voice_id_configured": True,
                "fallback_used": False,
                "error": None,
                "latency_ms": 0,
                "text": safe_text,
            }

        result = self.synthesize(safe_text)
        if not result.get("ok"):
            return self._failed(
                "failed",
                result.get("error_message") or result.get("error_type") or "fish_audio_failed",
                result.get("status_code"),
                result.get("latency_ms"),
                safe_text,
                error_type=result.get("error_type"),
                retry_count=result.get("retry_count", 0),
                fix=result.get("fix"),
            )

        try:
            self._play_audio(result["audio"], str(result.get("format") or "wav"))
        except Exception as exc:
            return self._failed(
                "playback_failed",
                exc.__class__.__name__,
                result.get("status_code"),
                result.get("latency_ms"),
                safe_text,
                audio_available=True,
                audio_bytes=result.get("audio_bytes"),
                error_type="playback_failed",
                retry_count=result.get("retry_count", 0),
                fix=_fix_for(result.get("status_code"), "playback_failed"),
            )

        return {
            "mode": "fish_audio",
            "provider": "fish_audio",
            "requested": True,
            "called": True,
            "spoken": True,
            "played": True,
            "ok": True,
            "audio_available": True,
            "status": "completed",
            "status_code": result.get("status_code"),
            "audio_bytes": result.get("audio_bytes"),
            "format": result.get("format"),
            "fallback_used": False,
            "error": None,
            "error_type": None,
            "latency_ms": result.get("latency_ms"),
            "retry_count": result.get("retry_count", 0),
            "text": safe_text,
        }

    def _failed_result(
        self,
        status_code: int | None,
        error_type: str,
        message: str,
        latency_ms: int,
        retry_count: int,
        text: str,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "provider": "fish_audio",
            "endpoint": self.endpoint,
            "called": True,
            "status_code": status_code,
            "error_type": error_type,
            "error_message": message,
            "fix": _fix_for(status_code, error_type),
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "text": text,
        }

    def _failed(
        self,
        status: str,
        error: str,
        status_code: int | None,
        latency_ms: int | None,
        text: str,
        *,
        audio_available: bool = False,
        audio_bytes: int | None = None,
        error_type: str | None = None,
        retry_count: int = 0,
        fix: str | None = None,
        called: bool = True,
    ) -> dict[str, Any]:
        return {
            "mode": "fish_audio",
            "provider": "fish_audio",
            "requested": True,
            "called": called,
            "spoken": False,
            "played": False,
            "ok": False,
            "audio_available": audio_available,
            "status": status,
            "status_code": status_code,
            "audio_bytes": audio_bytes,
            "fallback_used": False,
            "error": error,
            "error_type": error_type or status,
            "fix": fix or _fix_for(status_code, error_type or status),
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "text": text,
        }

    @staticmethod
    def _tts_text(text: str) -> str:
        safe_text = (text or "").strip() or "\u041a\u043e\u043c\u0430\u043d\u0434\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430."
        return safe_text[:500]

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _play_audio(audio: bytes, audio_format: str) -> None:
        suffix = ".mp3" if audio_format == "mp3" else ".wav"
        temp_path = Path(tempfile.gettempdir()) / f"jarvis_pc_v2_tts{suffix}"
        temp_path.write_bytes(audio)
        if suffix == ".wav":
            winsound.PlaySound(str(temp_path), winsound.SND_FILENAME)
            return
        raise RuntimeError("mp3 playback is not supported by winsound")

    @staticmethod
    def _extract_error_message(body: str) -> str | None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body[:500] if body else None
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or error)
            if error:
                return str(error)
            if data.get("message"):
                return str(data["message"])
        return body[:500] if body else None

    def _log_failure(
        self,
        fish_logger: logging.Logger,
        provider_logger: logging.Logger,
        status_code: int | None,
        latency_ms: int,
        error_type: str,
        message: str,
        retry_count: int,
    ) -> None:
        fish_logger.info(
            "[FISH] status_code=%s latency_ms=%s audio_bytes=0 error_type=%s error_message=%s retry_count=%s",
            status_code,
            latency_ms,
            error_type,
            message,
            retry_count,
        )
        provider_logger.info(
            "[FISH] status_code=%s latency_ms=%s audio_bytes=0 error_type=%s error_message=%s retry_count=%s",
            status_code,
            latency_ms,
            error_type,
            message,
            retry_count,
        )
