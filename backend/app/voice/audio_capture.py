from __future__ import annotations

import importlib.util
import logging
import math
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger("jarvis.audio_capture")

INSTALL_HINT = r".venv\Scripts\python.exe -m pip install -r requirements.txt"
WINDOWS_AUDIO_HOST_FIX = (
    "\u0417\u0430\u043a\u0440\u043e\u0439\u0442\u0435 Telegram/Discord/\u0431\u0440\u0430\u0443\u0437\u0435\u0440/OBS, "
    "\u043e\u0442\u043a\u043b\u044e\u0447\u0438\u0442\u0435 \u043c\u043e\u043d\u043e\u043f\u043e\u043b\u044c\u043d\u044b\u0439 \u0440\u0435\u0436\u0438\u043c \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0430 \u0432 Windows, "
    "\u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 ME6S device, "
    "\u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 Windows Audio service."
)


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
    device: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class OpenedInputStream:
    stream: Any
    device: dict[str, Any]
    samplerate: int
    channels: int
    attempts: list[dict[str, Any]]

    def close(self) -> None:
        try:
            self.stream.stop()
        except Exception:
            pass
        try:
            self.stream.close()
        except Exception:
            pass


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
    for enc in ("cp1252", "latin-1"):
        try:
            raw = name.encode(enc)
        except Exception:
            continue
        for target in ("utf-8", "cp1251"):
            try:
                decoded = raw.decode(target)
            except Exception:
                continue
            if any(ord(char) > 127 for char in decoded):
                return decoded
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        name = name.encode("utf-8", errors="replace").decode("utf-8")
    return name


def _require_sounddevice() -> Any:
    if not sounddevice_available():
        raise VoiceDependencyError(
            "SOUNDDEVICE_NOT_INSTALLED",
            "sounddevice is not installed. Install backend dependencies.",
            {"install_hint": INSTALL_HINT, "error_type": "microphone_open_failed"},
        )
    import sounddevice as sd

    return sd


def _require_numpy() -> Any:
    if not numpy_available():
        raise VoiceDependencyError(
            "NUMPY_NOT_INSTALLED",
            "numpy is not installed. Install backend dependencies.",
            {"install_hint": INSTALL_HINT, "error_type": "microphone_open_failed"},
        )
    import numpy as np

    return np


def _query_hostapi_name(sd: Any, hostapi_index: Any) -> str:
    try:
        if hostapi_index is None:
            return ""
        hostapi = sd.query_hostapis(int(hostapi_index))
        if isinstance(hostapi, dict):
            return str(hostapi.get("name") or "")
    except Exception:
        pass
    return ""


def _default_input_index(sd: Any) -> int | None:
    try:
        default_device = sd.default.device
        if default_device and default_device[0] is not None and int(default_device[0]) >= 0:
            return int(default_device[0])
    except Exception:
        pass
    return None


def _raw_devices(sd: Any) -> list[dict[str, Any]]:
    raw = sd.query_devices()
    if isinstance(raw, dict):
        return [raw]
    return list(raw)


def _device_dict(index: int, device: dict[str, Any], sd: Any, default_input: int | None) -> dict[str, Any]:
    channels = int(device.get("max_input_channels", 0) or 0)
    hostapi_index = device.get("hostapi")
    return {
        "id": str(index),
        "device_id": str(index),
        "index": index,
        "name": clean_device_name(str(device.get("name", f"Input device {index}"))),
        "hostapi": _query_hostapi_name(sd, hostapi_index),
        "hostapi_index": hostapi_index,
        "channels": channels,
        "max_input_channels": channels,
        "default": index == default_input,
        "default_samplerate": float(device.get("default_samplerate", 44100.0) or 44100.0),
    }


def list_input_devices() -> list[dict[str, Any]]:
    sd = _require_sounddevice()
    default_input = _default_input_index(sd)
    devices: list[dict[str, Any]] = []
    for index, device in enumerate(_raw_devices(sd)):
        channels = int(device.get("max_input_channels", 0) or 0)
        if channels <= 0:
            continue
        devices.append(_device_dict(index, device, sd, default_input))
    return devices


def _settings_device_id(settings: Any) -> str:
    return str(getattr(settings, "listener_device_id", "default") or "default")


def _coerce_settings_and_device(settings_or_device_id: Any = None, device_id: str | int | None = None) -> tuple[Any | None, str | int | None]:
    if hasattr(settings_or_device_id, "listener_device_id"):
        return settings_or_device_id, device_id if device_id is not None else _settings_device_id(settings_or_device_id)
    return None, settings_or_device_id if device_id is None else device_id


def _find_by_id(devices: list[dict[str, Any]], device_id: str | int | None) -> dict[str, Any] | None:
    if device_id in {None, "", "default"}:
        return None
    raw = str(device_id).strip().lower()
    for device in devices:
        if raw == str(device["id"]).lower():
            return device
    try:
        index = int(raw)
    except ValueError:
        index = -1
    for device in devices:
        if int(device["index"]) == index:
            return device
    return None


def _find_by_name(devices: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    needle = clean_device_name(str(name or "")).strip().lower()
    if not needle:
        return None
    for device in devices:
        candidate = str(device["name"]).lower()
        if candidate == needle or needle in candidate or candidate in needle:
            return device
    return None


def _find_contains(devices: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    lowered = needle.lower()
    for device in devices:
        if lowered in str(device["name"]).lower():
            return device
    return None


def _default_device(devices: list[dict[str, Any]]) -> dict[str, Any] | None:
    for device in devices:
        if device.get("default"):
            return device
    return devices[0] if devices else None


def resolve_input_device(settings_or_device_id: Any = None, device_id: str | int | None = None) -> dict[str, Any]:
    settings, selected_id = _coerce_settings_and_device(settings_or_device_id, device_id)
    try:
        devices = list_input_devices()
    except VoiceDependencyError as exc:
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "hostapi": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": exc.details.get("error_type") or "microphone_open_failed",
            "fix": exc.details.get("install_hint") or "Install sounddevice and numpy.",
        }
    except Exception as exc:
        diagnosis = diagnose_microphone_error(exc)
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "hostapi": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": diagnosis["error_type"],
            "fix": diagnosis["fixes"][0],
        }

    if not devices:
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "hostapi": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": "microphone_device_not_found",
            "fix": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u0435 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u0438\u043b\u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0435 input-\u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e.",
        }

    device = _find_by_id(devices, selected_id)
    if device is None and settings is not None:
        device = _find_by_name(devices, getattr(settings, "listener_device_name", None))
    if device is None:
        device = _find_contains(devices, "ME6S")
    if device is None:
        device = _default_device(devices)

    if device is None:
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "hostapi": None,
            "sample_rate": 16000,
            "channels": 1,
            "error_type": "microphone_device_not_found",
            "fix": f"Selected input device '{selected_id}' was not found.",
        }

    return {
        "ok": True,
        "device_id": int(device["index"]),
        "device_name": device["name"],
        "hostapi": device.get("hostapi") or "",
        "hostapi_index": device.get("hostapi_index"),
        "sample_rate": int(float(device.get("default_samplerate") or 44100)),
        "channels": 1 if int(device.get("channels") or 1) >= 1 else 0,
        "max_input_channels": int(device.get("channels") or 1),
        "default_samplerate": float(device.get("default_samplerate") or 44100.0),
        "error_type": None,
        "fix": None,
    }


def diagnose_microphone_error(error: BaseException | str | None) -> dict[str, Any]:
    message = str(error or "")
    lowered = message.lower()
    error_type = "microphone_open_failed"
    if any(marker in lowered for marker in ("-9999", "wdmsyncioctl", "deviceiocontrol", "0x00000490", "unanticipated host error")):
        error_type = "windows_audio_host_error"
    elif any(marker in lowered for marker in ("permission", "access denied", "privacy", "denied")):
        error_type = "microphone_permission_denied"
    elif any(marker in lowered for marker in ("busy", "unavailable", "already in use")):
        error_type = "microphone_busy"
    elif any(marker in lowered for marker in ("invalid sample rate", "samplerate", "sample rate")):
        error_type = "microphone_invalid_samplerate"
    elif any(marker in lowered for marker in ("invalid number of channels", "channels")):
        error_type = "microphone_invalid_channels"
    elif any(marker in lowered for marker in ("not found", "invalid device", "device unavailable")):
        error_type = "microphone_device_not_found"
    elif not message:
        error_type = "microphone_unknown_host_error"

    fixes = {
        "windows_audio_host_error": [WINDOWS_AUDIO_HOST_FIX],
        "microphone_permission_denied": [
            "\u0420\u0430\u0437\u0440\u0435\u0448\u0438\u0442\u0435 \u0434\u043e\u0441\u0442\u0443\u043f \u043a \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0443 \u0432 Windows Privacy settings \u0434\u043b\u044f desktop apps."
        ],
        "microphone_busy": [WINDOWS_AUDIO_HOST_FIX],
        "microphone_invalid_samplerate": [
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 sample rate 44100/48000 Hz \u0438\u043b\u0438 \u0434\u0440\u0443\u0433\u043e\u0439 input device."
        ],
        "microphone_invalid_channels": [
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 mono input \u0438\u043b\u0438 \u0434\u0440\u0443\u0433\u043e\u0439 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d."
        ],
        "microphone_device_not_found": [
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u0437\u0430\u043d\u043e\u0432\u043e: device_id \u0438\u0437 Windows \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u0441\u044f."
        ],
        "microphone_open_failed": [WINDOWS_AUDIO_HOST_FIX],
        "microphone_unknown_host_error": [WINDOWS_AUDIO_HOST_FIX],
        "microphone_no_audio": [
            "\u0423\u0432\u0435\u043b\u0438\u0447\u044c\u0442\u0435 \u0443\u0440\u043e\u0432\u0435\u043d\u044c \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0430 \u0438 \u0441\u043a\u0430\u0436\u0438\u0442\u0435 \u0444\u0440\u0430\u0437\u0443 \u0433\u0440\u043e\u043c\u0447\u0435."
        ],
    }
    return {
        "error_type": error_type,
        "error": message,
        "fixes": fixes.get(error_type, [WINDOWS_AUDIO_HOST_FIX]),
    }


def _attempt_template(number: int, device: dict[str, Any] | None, samplerate: int, channels: int) -> dict[str, Any]:
    return {
        "attempt": number,
        "device_id": str(device.get("id") if device else "default"),
        "device_name": str(device.get("name") if device else "default input"),
        "samplerate": int(samplerate),
        "channels": int(channels),
        "hostapi": str(device.get("hostapi") or "") if device else "",
        "ok": False,
        "error_type": None,
        "error": None,
    }


def _unique_attempts(raw_attempts: list[tuple[dict[str, Any] | None, int, int]]) -> list[tuple[dict[str, Any] | None, int, int]]:
    unique: list[tuple[dict[str, Any] | None, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for device, samplerate, channels in raw_attempts:
        key = (str(device.get("id") if device else "default"), int(samplerate), int(channels))
        if key in seen:
            continue
        seen.add(key)
        unique.append((device, samplerate, channels))
    return unique


def safe_open_input_stream(
    *,
    settings: Any | None = None,
    device_id: str | int | None = None,
    samplerate: int = 16000,
    channels: int = 1,
    dtype: str = "float32",
) -> OpenedInputStream:
    sd = _require_sounddevice()
    devices = list_input_devices()
    selected_id = device_id if device_id is not None else (_settings_device_id(settings) if settings is not None else "default")
    selected = _find_by_id(devices, selected_id)
    if selected is None and selected_id in {None, "", "default"}:
        selected = _default_device(devices)
    saved_name = getattr(settings, "listener_device_name", None) if settings is not None else None
    by_name = _find_by_name(devices, saved_name)
    by_me6s = _find_contains(devices, "ME6S")
    default = _default_device(devices)

    if selected is None:
        selected = by_name or by_me6s or default
    if selected is None:
        diagnosis = diagnose_microphone_error("No input devices found")
        raise VoiceDependencyError(
            diagnosis["error_type"].upper(),
            diagnosis["error"],
            {"attempts": [], "fixes": diagnosis["fixes"], "error_type": diagnosis["error_type"]},
        )

    selected_default_rate = int(float(selected.get("default_samplerate") or samplerate or 44100))
    raw_attempts = [
        (selected, 16000, 1),
        (selected, selected_default_rate, 1),
        (selected, 44100, 1),
        (selected, 48000, 1),
        (selected, 44100, 2),
        (selected, 48000, 2),
        (default, 44100, 1),
        (default, 48000, 1),
        (by_name, int(float((by_name or selected).get("default_samplerate") or 44100)), 1),
        (by_me6s, int(float((by_me6s or selected).get("default_samplerate") or 44100)), 1),
    ]
    attempts: list[dict[str, Any]] = []

    for device, rate, channel_count in [(dev, sr, ch) for dev, sr, ch in raw_attempts if dev is not None]:
        attempt = _attempt_template(len(attempts) + 1, device, rate, channel_count)
        attempts.append(attempt)
        try:
            stream = sd.InputStream(
                device=int(device["index"]),
                samplerate=int(rate),
                channels=int(channel_count),
                dtype=dtype,
            )
            stream.start()
            attempt["ok"] = True
            logger.info("[AUDIO_CAPTURE] open attempt succeeded: %s", attempt)
            return OpenedInputStream(
                stream=stream,
                device=device,
                samplerate=int(rate),
                channels=int(channel_count),
                attempts=attempts,
            )
        except Exception as exc:
            diagnosis = diagnose_microphone_error(exc)
            attempt["error_type"] = diagnosis["error_type"]
            attempt["error"] = diagnosis["error"]
            logger.warning("[AUDIO_CAPTURE] open attempt failed: %s", attempt)

    final = attempts[-1] if attempts else {"error_type": "microphone_open_failed", "error": "No attempts were made."}
    diagnosis = diagnose_microphone_error(str(final.get("error") or "microphone open failed"))
    raise VoiceDependencyError(
        str(final.get("error_type") or diagnosis["error_type"]).upper(),
        str(final.get("error") or "Microphone input stream could not be opened."),
        {
            "attempts": attempts,
            "fixes": diagnosis["fixes"],
            "error_type": final.get("error_type") or diagnosis["error_type"],
        },
    )


def measure_audio_level(samples: Any) -> dict[str, float]:
    np = _require_numpy()
    if samples is None:
        return {"rms": 0.0, "peak": 0.0}
    arr = np.asarray(samples, dtype="float32")
    if arr.size == 0:
        return {"rms": 0.0, "peak": 0.0}
    rms = float(math.sqrt(float(np.mean(np.square(arr)))))
    peak = float(np.max(np.abs(arr)))
    return {"rms": rms, "peak": peak}


def _resample_and_channel(samples: Any, source_rate: int, target_rate: int, target_channels: int) -> Any:
    np = _require_numpy()
    arr = np.asarray(samples, dtype="float32")
    if arr.ndim > 1 and arr.shape[1] > 1:
        arr = np.mean(arr, axis=1)
    else:
        arr = arr.reshape(-1)
    if int(source_rate) != int(target_rate) and arr.size > 0:
        duration = arr.size / float(source_rate)
        target_count = max(1, int(duration * int(target_rate)))
        x_original = np.linspace(0.0, duration, arr.size, endpoint=False)
        x_target = np.linspace(0.0, duration, target_count, endpoint=False)
        arr = np.interp(x_target, x_original, arr).astype("float32")
    if target_channels > 1:
        arr = np.repeat(arr.reshape(-1, 1), target_channels, axis=1)
    else:
        arr = arr.reshape(-1, 1)
    return arr


def record_short_audio(
    *,
    settings: Any | None = None,
    device_id: str | int | None = None,
    duration_seconds: float = 3,
    sample_rate: int = 16000,
    channels: int = 1,
) -> AudioCapture:
    if duration_seconds <= 0:
        raise VoiceDependencyError("INVALID_DURATION", "duration_seconds must be greater than zero.")
    _require_numpy()
    opened = safe_open_input_stream(settings=settings, device_id=device_id, samplerate=sample_rate, channels=channels)
    try:
        frames = max(1, int(opened.samplerate * duration_seconds))
        samples, _overflowed = opened.stream.read(frames)
    finally:
        opened.close()
    converted = _resample_and_channel(samples, opened.samplerate, sample_rate, channels)
    levels = measure_audio_level(converted)
    if converted is None or len(converted) == 0:
        raise VoiceDependencyError("MICROPHONE_NO_AUDIO", "Microphone returned no audio.", {"error_type": "microphone_no_audio"})
    return AudioCapture(
        sample_rate=sample_rate,
        channels=channels,
        samples=converted,
        rms=levels["rms"],
        peak=levels["peak"],
        device=opened.device,
        attempts=opened.attempts,
    )


def capture_audio(
    *,
    device_id: str | int | None = "default",
    duration_seconds: float = 3,
    sample_rate: int = 16000,
    channels: int = 1,
) -> AudioCapture:
    return record_short_audio(
        device_id=device_id,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
    )


def test_microphone(device_id: str | int | None = "default", duration_seconds: float = 3) -> dict[str, Any]:
    capture = capture_audio(device_id=device_id, duration_seconds=duration_seconds)
    return {
        "device_id": str(device_id) if device_id is not None else "default",
        "opened_device": capture.device,
        "attempts": capture.attempts or [],
        "duration_seconds": duration_seconds,
        "sample_rate": capture.sample_rate,
        "channels": capture.channels,
        "rms": capture.rms,
        "peak": capture.peak,
        "heard_signal": capture.rms > 0.005 or capture.peak > 0.02,
    }


def debug_open_microphone(
    *,
    settings: Any | None = None,
    device_id: str | int | None = "default",
    duration_seconds: float = 3,
) -> dict[str, Any]:
    selected = resolve_input_device(settings, device_id=device_id) if settings is not None else resolve_input_device(device_id)
    data = {
        "selected_device": selected if selected.get("ok") else None,
        "opened_device": None,
        "attempts": [],
        "rms": 0.0,
        "peak": 0.0,
        "heard_signal": False,
        "final_error_type": None,
        "final_error": None,
        "fixes": [],
    }
    try:
        capture = record_short_audio(settings=settings, device_id=device_id, duration_seconds=duration_seconds)
        data.update(
            {
                "opened_device": capture.device,
                "attempts": capture.attempts or [],
                "rms": capture.rms,
                "peak": capture.peak,
                "heard_signal": capture.rms > 0.005 or capture.peak > 0.02,
            }
        )
        if not data["heard_signal"]:
            diagnosis = diagnose_microphone_error("microphone_no_audio")
            data["final_error_type"] = "microphone_no_audio"
            data["final_error"] = "Microphone opened, but no audible signal was detected."
            data["fixes"] = diagnosis["fixes"]
        return data
    except VoiceDependencyError as exc:
        details = exc.details if isinstance(exc.details, dict) else {}
        attempts = details.get("attempts") or []
        diagnosis = diagnose_microphone_error(exc.message)
        final_type = details.get("error_type") or diagnosis["error_type"]
        data.update(
            {
                "attempts": attempts,
                "final_error_type": final_type,
                "final_error": exc.message,
                "fixes": details.get("fixes") or diagnosis["fixes"],
            }
        )
        return data
    except Exception as exc:
        diagnosis = diagnose_microphone_error(exc)
        data.update(
            {
                "final_error_type": diagnosis["error_type"],
                "final_error": diagnosis["error"],
                "fixes": diagnosis["fixes"],
            }
        )
        return data


def mic_diagnostics() -> dict[str, Any]:
    sd_ok = sounddevice_available()
    np_ok = numpy_available()
    devices: list[dict[str, Any]] = []
    default_device = None
    fixes: list[str] = []

    if not sd_ok:
        fixes.append("Install sounddevice: pip install sounddevice")
    if not np_ok:
        fixes.append("Install numpy: pip install numpy")
    if sd_ok:
        try:
            devices = list_input_devices()
            default_device = next((device for device in devices if device.get("default")), None)
        except Exception as exc:
            diagnosis = diagnose_microphone_error(exc)
            fixes.extend(diagnosis["fixes"])

    if sd_ok and np_ok and not devices:
        fixes.append("\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u0435 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u043a \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0443.")

    return {
        "sounddevice_available": sd_ok,
        "numpy_available": np_ok,
        "default_input_device": default_device,
        "input_devices": devices,
        "windows_hint": WINDOWS_AUDIO_HOST_FIX,
        "can_record": sd_ok and np_ok and bool(devices),
        "fixes": fixes,
    }
