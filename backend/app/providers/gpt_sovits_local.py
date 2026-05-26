from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings


class GPTSoVITSLocalTTS:
    """Optional adapter for an external GPT-SoVITS server."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> dict[str, Any]:
        if not self.settings.gpt_sovits_enabled:
            return {
                "enabled": False,
                "available": False,
                "api_url": self.settings.gpt_sovits_api_url,
                "fix": "Set JARVIS_GPT_SOVITS_ENABLED=true after starting the external GPT-SoVITS server.",
            }
        try:
            response = httpx.get(self.settings.gpt_sovits_api_url, timeout=1.5)
            available = response.status_code < 500
            return {
                "enabled": True,
                "available": available,
                "api_url": self.settings.gpt_sovits_api_url,
                "status_code": response.status_code,
                "fix": None if available else "GPT-SoVITS server responded with an error.",
            }
        except Exception:
            return {
                "enabled": True,
                "available": False,
                "api_url": self.settings.gpt_sovits_api_url,
                "error_type": "gpt_sovits_api_unreachable",
                "fix": "GPT-SoVITS сервер не запущен. Откройте docs/local_voice_engines.md.",
            }

    def synthesize(self, text: str) -> dict[str, Any]:
        started = time.perf_counter()
        status = self.status()
        if not self.settings.gpt_sovits_enabled:
            return self._failure(text, "gpt_sovits_disabled", "GPT-SoVITS is disabled.", status, started)
        if not status.get("available"):
            return self._failure(
                text,
                "gpt_sovits_api_unreachable",
                "GPT-SoVITS API is unreachable.",
                status,
                started,
            )

        payload = {
            "text": text,
            "text_lang": self.settings.gpt_sovits_text_lang,
            "refer_wav_path": self.settings.gpt_sovits_refer_wav,
            "prompt_text": self.settings.gpt_sovits_prompt_text,
            "prompt_lang": self.settings.gpt_sovits_prompt_lang,
        }
        try:
            response = httpx.post(self.settings.gpt_sovits_api_url, json=payload, timeout=60)
            response.raise_for_status()
            audio = response.content
            if not audio:
                return self._failure(text, "gpt_sovits_generation_failed", "GPT-SoVITS returned empty audio.", status, started)
            return {
                "ok": True,
                "called": True,
                "status": "completed",
                "spoken": False,
                "played": False,
                "provider": "gpt_sovits_local",
                "audio": audio,
                "audio_bytes": len(audio),
                "format": "wav",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "text": text,
            }
        except httpx.RequestError as exc:
            return self._failure(text, "gpt_sovits_api_unreachable", str(exc), status, started)
        except Exception as exc:
            return self._failure(text, "gpt_sovits_generation_failed", str(exc), status, started)

    def _failure(self, text: str, error_type: str, error: str, status: dict[str, Any], started: float) -> dict[str, Any]:
        return {
            "ok": False,
            "called": True,
            "status": "failed",
            "spoken": False,
            "played": False,
            "provider": "gpt_sovits_local",
            "error_type": error_type,
            "error": error,
            "fix": status.get("fix"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "text": text,
        }
