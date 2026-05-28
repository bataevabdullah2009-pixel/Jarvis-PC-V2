from __future__ import annotations

from app.voice.audio_capture import (
    INSTALL_HINT,
    AudioCapture,
    OpenedInputStream,
    VoiceDependencyError,
    capture_audio,
    clean_device_name,
    debug_open_microphone,
    dependency_check,
    diagnose_microphone_error,
    list_input_devices,
    measure_audio_level,
    mic_diagnostics,
    numpy_available,
    record_short_audio,
    resolve_input_device,
    safe_open_input_stream,
    sounddevice_available,
)


__all__ = [
    "INSTALL_HINT",
    "AudioCapture",
    "OpenedInputStream",
    "VoiceDependencyError",
    "capture_audio",
    "clean_device_name",
    "debug_open_microphone",
    "dependency_check",
    "diagnose_microphone_error",
    "list_input_devices",
    "measure_audio_level",
    "mic_diagnostics",
    "numpy_available",
    "record_short_audio",
    "resolve_input_device",
    "safe_open_input_stream",
    "sounddevice_available",
    "test_microphone",
]


def test_microphone(device_id: str | int | None = "default", duration_seconds: float = 3) -> dict:
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
