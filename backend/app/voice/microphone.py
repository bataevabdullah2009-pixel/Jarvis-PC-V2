from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any


INSTALL_HINT = r".venv\Scripts\python.exe -m pip install -r requirements.txt"


class VoiceDependencyError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(slots=True)
class AudioCapture:
    sample_rate: int
    channels: int
    samples: Any
    rms: float
    peak: float


def sounddevice_available() -> bool:
    return importlib.util.find_spec("sounddevice") is not None


def numpy_available() -> bool:
    return importlib.util.find_spec("numpy") is not None


def dependency_check() -> dict[str, Any]:
    sd_available = sounddevice_available()
    np_available = numpy_available()
    return {
        "sounddevice": {
            "available": sd_available,
            "install_hint": None if sd_available else INSTALL_HINT,
        },
        "numpy": {
            "available": np_available,
            "install_hint": None if np_available else INSTALL_HINT,
        },
        "microphone": {
            "can_test": sd_available and np_available,
        },
    }


def list_input_devices() -> list[dict[str, Any]]:
    if not sounddevice_available():
        raise VoiceDependencyError(
            "SOUNDDEVICE_NOT_INSTALLED",
            "sounddevice не установлен. Установите зависимости backend.",
            {"install_hint": INSTALL_HINT},
        )

    import sounddevice as sd

    devices = sd.query_devices()
    default_input = sd.default.device[0] if sd.default.device else None
    result: list[dict[str, Any]] = []

    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0))
        if channels <= 0:
            continue
        result.append(
            {
                "id": str(index),
                "name": str(device.get("name", f"Input device {index}")),
                "channels": channels,
                "default": index == default_input,
                "default_samplerate": float(device.get("default_samplerate", 44100.0)),
            }
        )

    return result


def capture_audio(
    *,
    device_id: str | None = "default",
    duration_seconds: float = 3,
    sample_rate: int = 16000,
    channels: int = 1,
) -> AudioCapture:
    if not sounddevice_available():
        raise VoiceDependencyError(
            "SOUNDDEVICE_NOT_INSTALLED",
            "sounddevice не установлен. Установите зависимости backend.",
            {"install_hint": INSTALL_HINT},
        )
    if not numpy_available():
        raise VoiceDependencyError(
            "NUMPY_NOT_INSTALLED",
            "numpy не установлен. Установите зависимости backend.",
            {"install_hint": INSTALL_HINT},
        )

    import numpy as np
    import sounddevice as sd

    if duration_seconds <= 0:
        raise VoiceDependencyError("INVALID_DURATION", "duration_seconds должен быть больше нуля.")

    device = None if device_id in {None, "", "default"} else int(str(device_id))
    frames = int(sample_rate * duration_seconds)

    try:
        samples = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32", device=device)
        sd.wait()
    except Exception as exc:
        raise VoiceDependencyError("MICROPHONE_CAPTURE_FAILED", "Не удалось записать звук с микрофона.", {"error": exc.__class__.__name__}) from exc

    if samples is None or len(samples) == 0:
        raise VoiceDependencyError("MICROPHONE_NO_AUDIO", "Микрофон не вернул аудио.")

    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    return AudioCapture(sample_rate=sample_rate, channels=channels, samples=samples, rms=rms, peak=peak)


def test_microphone(device_id: str | None = "default", duration_seconds: float = 3) -> dict[str, Any]:
    capture = capture_audio(device_id=device_id, duration_seconds=duration_seconds)
    return {
        "device_id": device_id or "default",
        "duration_seconds": duration_seconds,
        "sample_rate": capture.sample_rate,
        "channels": capture.channels,
        "rms": capture.rms,
        "peak": capture.peak,
        "heard_signal": capture.rms > 0.005 or capture.peak > 0.02,
    }


def mic_diagnostics() -> dict[str, Any]:
    sd_ok = sounddevice_available()
    np_ok = numpy_available()

    devices = []
    default_device = None
    fixes = []

    if not sd_ok:
        fixes.append("Установите sounddevice: pip install sounddevice")
    if not np_ok:
        fixes.append("Установите numpy: pip install numpy")

    if sd_ok:
        try:
            import sounddevice as sd
            raw_devices = sd.query_devices()
            default_input_idx = sd.default.device[0] if (sd.default.device and len(sd.default.device) > 0) else None

            for index, device in enumerate(raw_devices):
                channels = int(device.get("max_input_channels", 0))
                if channels <= 0:
                    continue
                dev_dict = {
                    "id": str(index),
                    "name": str(device.get("name", f"Input device {index}")),
                    "channels": channels,
                    "default": index == default_input_idx,
                    "default_samplerate": float(device.get("default_samplerate", 44100.0)),
                }
                devices.append(dev_dict)
                if index == default_input_idx:
                    default_device = dev_dict
        except Exception as exc:
            fixes.append(f"Ошибка опроса звуковых устройств: {exc}")

    if sd_ok and np_ok and not devices:
        fixes.append("Подключите микрофон к компьютеру.")

    can_record = sd_ok and np_ok and len(devices) > 0

    return {
        "sounddevice_available": sd_ok,
        "numpy_available": np_ok,
        "default_input_device": default_device,
        "input_devices": devices,
        "windows_hint": "Убедитесь, что в параметрах конфиденциальности Windows разрешен доступ к микрофону для классических приложений.",
        "can_record": can_record,
        "fixes": fixes,
    }

