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


def clean_device_name(name: str) -> str:
    if not name:
        return name
    # If the string was incorrectly decoded as latin-1 or cp1252 but was actually cp1251 (or utf-8):
    for enc in ("cp1252", "latin-1"):
        try:
            b = name.encode(enc)
            # Try utf-8 first
            try:
                decoded = b.decode("utf-8")
                if any(ord(c) > 127 for c in decoded):
                    return decoded
            except Exception:
                pass
            # Try cp1251 (Cyrillic)
            try:
                decoded = b.decode("cp1251")
                if any(1040 <= ord(c) <= 1103 for c in decoded):
                    return decoded
            except Exception:
                pass
        except Exception:
            pass

    # Ensure it's safe for UTF-8 JSON serialization
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        name = name.encode("utf-8", errors="replace").decode("utf-8")

    return name


def resolve_input_device(device_id: str | int | None) -> dict[str, Any]:
    if not sounddevice_available():
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": "no_input_devices",
            "fix": "sounddevice не установлен. Установите зависимости backend.",
        }

    import sounddevice as sd
    try:
        raw_devices = sd.query_devices()
    except Exception as e:
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": "no_input_devices",
            "fix": f"Ошибка опроса звуковых устройств: {e}",
        }

    input_devices = []
    default_input_idx = None
    try:
        if sd.default.device and sd.default.device[0] is not None:
            default_input_idx = sd.default.device[0]
    except Exception:
        pass

    for index, device in enumerate(raw_devices):
        channels = int(device.get("max_input_channels", 0))
        if channels > 0:
            input_devices.append((index, device))

    if not input_devices:
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": "no_input_devices",
            "fix": "Входные аудиоустройства (микрофоны) не найдены. Подключите микрофон к компьютеру.",
        }

    target_idx = None
    if device_id in {None, "", "default"}:
        if default_input_idx is not None and 0 <= default_input_idx < len(raw_devices):
            if raw_devices[default_input_idx].get("max_input_channels", 0) > 0:
                target_idx = default_input_idx
        if target_idx is None:
            target_idx = input_devices[0][0]
    else:
        # Try parsing numeric ID
        try:
            parsed_id = int(str(device_id))
            if 0 <= parsed_id < len(raw_devices) and raw_devices[parsed_id].get("max_input_channels", 0) > 0:
                target_idx = parsed_id
        except ValueError:
            pass

        # Try match by name or index string
        if target_idx is None:
            device_id_str = str(device_id).lower()
            for idx, dev in input_devices:
                name_clean = clean_device_name(str(dev.get("name", ""))).lower()
                if device_id_str in name_clean or device_id_str == str(idx):
                    target_idx = idx
                    break

    if target_idx is None:
        available_ids = [str(idx) for idx, _ in input_devices]
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": "device_not_found",
            "fix": f"Устройство с ID '{device_id}' не найдено. Доступные ID: {', '.join(available_ids)}",
        }

    dev = raw_devices[target_idx]
    native_rate = int(dev.get("default_samplerate", 44100.0))
    channels = int(dev.get("max_input_channels", 1))
    preferred_channels = 1 if channels >= 1 else channels

    return {
        "ok": True,
        "device_id": target_idx,
        "device_name": clean_device_name(str(dev.get("name", f"Input device {target_idx}"))),
        "sample_rate": native_rate,
        "channels": preferred_channels,
        "error_type": None,
        "fix": None,
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
                "name": clean_device_name(str(device.get("name", f"Input device {index}"))),
                "channels": channels,
                "default": index == default_input,
                "default_samplerate": float(device.get("default_samplerate", 44100.0)),
            }
        )

    return result


def capture_audio(
    *,
    device_id: str | int | None = "default",
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

    # Resolve device characteristics
    res = resolve_input_device(device_id)
    if not res["ok"]:
        raise VoiceDependencyError(
            res["error_type"].upper(),
            res["fix"],
            {"device_id": device_id}
        )

    target_device = res["device_id"]
    native_rate = res["sample_rate"]
    native_channels = res["channels"]

    frames = int(native_rate * duration_seconds)

    try:
        samples = sd.rec(
            frames,
            samplerate=native_rate,
            channels=native_channels,
            dtype="float32",
            device=target_device
        )
        sd.wait()
    except Exception as exc:
        raise VoiceDependencyError(
            "MICROPHONE_CAPTURE_FAILED",
            f"Не удалось записать звук с микрофона: {exc}",
            {"error": exc.__class__.__name__}
        ) from exc

    if samples is None or len(samples) == 0:
        raise VoiceDependencyError("MICROPHONE_NO_AUDIO", "Микрофон не вернул аудио.")

    # Downmix / Resample to preferred sample_rate & channels if different
    if native_rate != sample_rate or native_channels != channels:
        duration = len(samples) / native_rate
        num_target_samples = int(duration * sample_rate)
        x_orig = np.linspace(0, duration, len(samples))
        x_target = np.linspace(0, duration, num_target_samples)

        # Average channels to mono if needed
        if len(samples.shape) > 1 and samples.shape[1] > 1:
            samples_mono = np.mean(samples, axis=1)
        else:
            samples_mono = samples.flatten()

        resampled = np.interp(x_target, x_orig, samples_mono)
        samples = resampled.reshape(-1, channels)

    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    return AudioCapture(sample_rate=sample_rate, channels=channels, samples=samples, rms=rms, peak=peak)


def test_microphone(device_id: str | int | None = "default", duration_seconds: float = 3) -> dict[str, Any]:
    capture = capture_audio(device_id=device_id, duration_seconds=duration_seconds)
    return {
        "device_id": str(device_id) if device_id is not None else "default",
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
            default_input_idx = None
            try:
                if sd.default.device and sd.default.device[0] is not None:
                    default_input_idx = sd.default.device[0]
            except Exception:
                pass

            for index, device in enumerate(raw_devices):
                channels = int(device.get("max_input_channels", 0))
                if channels <= 0:
                    continue
                dev_dict = {
                    "id": str(index),
                    "name": clean_device_name(str(device.get("name", f"Input device {index}"))),
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


