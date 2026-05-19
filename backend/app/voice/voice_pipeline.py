from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.router.command_router import CommandRouter
from app.voice.microphone import VoiceDependencyError, capture_audio, dependency_check, list_input_devices, test_microphone
from app.voice.stt import STTService, stt_dependency_status
from app.voice.wake import start_listener, stop_listener


class VoicePipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stt = STTService(settings)

    def dependency_check(self) -> dict[str, Any]:
        voice_dependencies = dependency_check()
        return {
            **voice_dependencies,
            "stt": stt_dependency_status(self.settings),
            "tts": {
                "mode": "fish_audio_primary",
                "providers": ["fish_audio", "text_only"] if self.settings.tts_require_fish_audio or not self.settings.tts_fallback_enabled else ["fish_audio", "pyttsx3", "text_only"],
                "fish_audio_configured": bool(self.settings.fish_audio_api_key and self.settings.fish_audio_voice_id),
                "offline_tts_available": False,
                "primary": self.settings.tts_primary,
                "fallback": self.settings.tts_fallback,
                "fallback_enabled": self.settings.tts_fallback_enabled,
                "require_fish_audio": self.settings.tts_require_fish_audio,
            },
        }

    def devices(self) -> dict[str, Any]:
        return {"input_devices": list_input_devices()}

    def test_microphone(self, *, device_id: str = "default", duration_seconds: float = 3) -> dict[str, Any]:
        return test_microphone(device_id=device_id, duration_seconds=duration_seconds)

    def record_command(
        self,
        *,
        device_id: str = "default",
        max_seconds: float = 8,
        send_to_assistant: bool = True,
        text_override: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if text_override:
            assistant_result = None
            if send_to_assistant:
                assistant_result = CommandRouter(self.settings).handle(
                    text_override,
                    source="voice",
                    context={"dry_run": dry_run},
                )
            return {
                "device_id": device_id,
                "duration_seconds": 0,
                "rms": None,
                "peak": None,
                "transcript": text_override,
                "stt": {"configured": True, "provider": "text_override"},
                "assistant_result": assistant_result,
            }

        capture = capture_audio(device_id=device_id, duration_seconds=max_seconds)
        stt_result = self.stt.transcribe(capture)
        transcript = stt_result.get("transcript")
        assistant_result = None

        if transcript and send_to_assistant:
            assistant_result = CommandRouter(self.settings).handle(
                str(transcript),
                source="voice",
                context={"dry_run": dry_run},
            )

        return {
            "device_id": device_id,
            "duration_seconds": max_seconds,
            "sample_rate": capture.sample_rate,
            "channels": capture.channels,
            "rms": capture.rms,
            "peak": capture.peak,
            "transcript": transcript,
            "stt": stt_result,
            "assistant_result": assistant_result,
        }

    def start_listener(self, *, wake_word: bool = True, clap: bool = True, device_id: str = "default") -> dict[str, Any]:
        return start_listener(wake_word=wake_word, clap=clap, device_id=device_id)

    def stop_listener(self) -> dict[str, Any]:
        return stop_listener()


def voice_error_response(exc: VoiceDependencyError) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        "details": exc.details,
    }
