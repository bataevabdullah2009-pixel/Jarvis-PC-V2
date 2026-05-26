from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT, Settings


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


class PiperLocalTTS:
    """Optional Piper integration. It never installs models during runtime."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> dict[str, Any]:
        model_path = _resolve_path(self.settings.piper_model_path)
        config_path = _resolve_path(self.settings.piper_config_path)
        exe_path = Path(self.settings.piper_exe_path) if self.settings.piper_exe_path else None
        package_exists = importlib.util.find_spec("piper") is not None or importlib.util.find_spec("piper_phonemize") is not None
        exe_exists = bool(exe_path and exe_path.exists())
        model_exists = model_path.exists()
        config_exists = config_path.exists()
        available = bool(self.settings.piper_enabled and model_exists and config_exists and (package_exists or exe_exists))
        return {
            "enabled": self.settings.piper_enabled,
            "available": available,
            "model_path": str(model_path),
            "config_path": str(config_path),
            "model_exists": model_exists,
            "config_exists": config_exists,
            "package_exists": package_exists,
            "exe_exists": exe_exists,
            "speaker_id": self.settings.piper_speaker_id,
            "install_hint": "Run tools/voice_engines/install_piper.ps1 and add Piper voice model files",
        }

    def synthesize(self, text: str) -> dict[str, Any]:
        started = time.perf_counter()
        status = self.status()
        if not self.settings.piper_enabled:
            return self._failure(text, "piper_disabled", "Piper is disabled.", status, started)
        if not status["model_exists"] or not status["config_exists"]:
            return self._failure(text, "piper_model_missing", "Piper model or config is missing.", status, started)
        if not status["available"]:
            return self._failure(text, "piper_not_installed", "Piper executable/package is missing.", status, started)

        exe = self.settings.piper_exe_path.strip()
        if not exe:
            return self._failure(text, "piper_exe_missing", "Set JARVIS_PIPER_EXE_PATH for local playback.", status, started)

        output_path = Path(tempfile.gettempdir()) / f"jarvis_piper_{int(time.time() * 1000)}.wav"
        command = [
            exe,
            "--model",
            status["model_path"],
            "--config",
            status["config_path"],
            "--output_file",
            str(output_path),
        ]
        if self.settings.piper_speaker_id:
            command.extend(["--speaker", self.settings.piper_speaker_id])

        try:
            subprocess.run(command, input=text, text=True, capture_output=True, timeout=45, check=True)
            audio = output_path.read_bytes()
            return {
                "ok": True,
                "called": True,
                "status": "completed",
                "spoken": False,
                "played": False,
                "audio": audio,
                "audio_bytes": len(audio),
                "format": "wav",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "provider": "piper_local",
                "text": text,
            }
        except Exception as exc:
            return self._failure(text, "piper_generation_failed", str(exc), status, started)
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _failure(self, text: str, error_type: str, error: str, status: dict[str, Any], started: float) -> dict[str, Any]:
        return {
            "ok": False,
            "called": True,
            "status": "failed",
            "spoken": False,
            "played": False,
            "provider": "piper_local",
            "error_type": error_type,
            "error": error,
            "fix": status.get("install_hint"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "text": text,
        }
