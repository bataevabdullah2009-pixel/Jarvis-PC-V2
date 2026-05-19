from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT, Settings
from app.voice.microphone import AudioCapture


def _resolve_model_path(settings: Settings) -> Path:
    model_path = Path(settings.vosk_model_path)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    return model_path


def stt_dependency_status(settings: Settings) -> dict[str, Any]:
    vosk_available = importlib.util.find_spec("vosk") is not None
    model_path = _resolve_model_path(settings)
    model_configured = vosk_available and model_path.exists()
    return {
        "configured": model_configured,
        "provider": "vosk" if model_configured else None,
        "offline": {
            "vosk_available": vosk_available,
            "model_configured": model_configured,
            "model_path": str(model_path),
            "install_hint": None if vosk_available else "pip install vosk",
        },
    }


class STTService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, capture: AudioCapture) -> dict[str, Any]:
        status = stt_dependency_status(self.settings)
        if status["configured"]:
            return self._transcribe_vosk(capture)

        return {
            "configured": False,
            "provider": None,
            "transcript": None,
            "error": {
                "code": "STT_NOT_CONFIGURED",
                "message": "STT пока не настроен. Микрофон проверен, но текст не распознан.",
            },
        }

    def _transcribe_vosk(self, capture: AudioCapture) -> dict[str, Any]:
        import numpy as np
        from vosk import KaldiRecognizer, Model

        model = Model(str(_resolve_model_path(self.settings)))
        recognizer = KaldiRecognizer(model, capture.sample_rate)

        samples = np.asarray(capture.samples)
        if samples.dtype != np.int16:
            samples = np.clip(samples, -1.0, 1.0)
            samples = (samples * 32767).astype(np.int16)

        recognizer.AcceptWaveform(samples.tobytes())
        result = json.loads(recognizer.FinalResult())
        transcript = str(result.get("text", "")).strip() or None

        return {
            "configured": True,
            "provider": "vosk",
            "transcript": transcript,
            "error": None if transcript else {
                "code": "STT_EMPTY_TRANSCRIPT",
                "message": "STT сработал, но речь не распознана.",
            },
        }
