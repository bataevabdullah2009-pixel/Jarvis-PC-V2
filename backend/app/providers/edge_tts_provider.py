from __future__ import annotations
import importlib.util
import time
from typing import Any
import anyio

from app.core.config import Settings


class EdgeTTSProvider:
    provider = "edge_tts"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return importlib.util.find_spec("edge_tts") is not None

    def synthesize(self, text: str) -> dict[str, Any]:
        started = time.perf_counter()
        if not self.available():
            return {
                "ok": False,
                "provider": "edge_tts",
                "error_type": "not_installed",
                "error_message": "edge-tts package is not installed.",
                "latency_ms": 0,
            }

        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")

            async def _stream():
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                return audio_data

            audio = anyio.from_thread.run(_stream)
            latency_ms = int((time.perf_counter() - started) * 1000)

            if not audio:
                return {
                    "ok": False,
                    "provider": "edge_tts",
                    "error_type": "empty_audio",
                    "error_message": "Edge TTS returned empty audio.",
                    "latency_ms": latency_ms,
                }

            return {
                "ok": True,
                "provider": "edge_tts",
                "audio": audio,
                "audio_bytes": len(audio),
                "format": "mp3",
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "ok": False,
                "provider": "edge_tts",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "latency_ms": latency_ms,
            }
