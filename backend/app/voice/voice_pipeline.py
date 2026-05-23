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
        device_id: str | int | None = "default",
        max_seconds: float = 8,
        send_to_assistant: bool = True,
        text_override: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        from app.voice.microphone import resolve_input_device

        # 1. Resolve input device
        dev_res = resolve_input_device(device_id)
        device_info = {
            "device_id": dev_res.get("device_id"),
            "device_name": dev_res.get("device_name"),
            "sample_rate": dev_res.get("sample_rate"),
            "channels": dev_res.get("channels"),
        }

        if text_override:
            assistant_result = None
            if send_to_assistant:
                from app.core.assistant_orchestrator import AssistantOrchestrator
                import asyncio
                import concurrent.futures

                async def run_ask():
                    return await AssistantOrchestrator(self.settings).ask(
                        text_override,
                        speak=True,
                        source="voice",
                        context={"dry_run": dry_run},
                    )

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(lambda: asyncio.run(run_ask()))
                            assistant_result = future.result()
                    else:
                        assistant_result = loop.run_until_complete(run_ask())
                except Exception:
                    assistant_result = asyncio.run(run_ask())

            return {
                "ok": True,
                "transcript": text_override,
                "final_status": "sent_to_assistant" if send_to_assistant else "recorded",
                "device": device_info,
                "capture": {
                    "ok": True,
                    "rms": 0.1,
                    "peak": 0.1,
                    "heard_signal": True
                },
                "stt": {
                    "configured": True,
                    "provider": "text_override",
                    "transcript": text_override,
                    "error_type": None,
                    "fix": None
                },
                "assistant_result": assistant_result,
            }

        if not dev_res["ok"]:
            return {
                "ok": False,
                "transcript": None,
                "final_status": "record_error",
                "device": device_info,
                "capture": {
                    "ok": False,
                    "rms": 0.0,
                    "peak": 0.0,
                    "heard_signal": False
                },
                "stt": {
                    "configured": False,
                    "provider": "vosk",
                    "transcript": None,
                    "error_type": dev_res.get("error_type"),
                    "fix": dev_res.get("fix")
                },
                "assistant_result": None,
            }

        # 2. Capture audio using resolve native parameters + resampling
        try:
            capture = capture_audio(device_id=device_id, duration_seconds=max_seconds)
            rms = capture.rms
            peak = capture.peak
            heard_signal = rms > 0.005 or peak > 0.02
        except Exception as exc:
            error_code = getattr(exc, "code", "CAPTURE_FAILED")
            fix_msg = "Проверьте выбранный микрофон, доступ Windows к микрофону, уровень громкости, разрешение для desktop apps."
            if isinstance(exc, VoiceDependencyError) and exc.details.get("install_hint"):
                fix_msg = f"Установите зависимости: {exc.details['install_hint']}"
            return {
                "ok": False,
                "transcript": None,
                "final_status": "record_error",
                "device": device_info,
                "capture": {
                    "ok": False,
                    "rms": 0.0,
                    "peak": 0.0,
                    "heard_signal": False
                },
                "stt": {
                    "configured": False,
                    "provider": "vosk",
                    "transcript": None,
                    "error_type": error_code,
                    "fix": fix_msg
                },
                "assistant_result": None,
            }

        # 3. Handle silence
        if not heard_signal:
            return {
                "ok": False,
                "transcript": None,
                "final_status": "no_audio",
                "device": device_info,
                "capture": {
                    "ok": True,
                    "rms": rms,
                    "peak": peak,
                    "heard_signal": False
                },
                "stt": {
                    "configured": False,
                    "provider": "vosk",
                    "transcript": None,
                    "error_type": "NO_AUDIO_HEARD",
                    "fix": "Микрофон не получает звук. Проверьте выбранный микрофон, уровень громкости, доступ Windows к микрофону."
                },
                "assistant_result": None,
            }

        # 4. Check if STT is configured
        stt_status_dict = stt_dependency_status(self.settings)
        if not stt_status_dict["configured"]:
            from app.voice.stt import _resolve_model_path
            model_path = _resolve_model_path(self.settings)
            return {
                "ok": False,
                "transcript": None,
                "final_status": "stt_not_configured",
                "device": device_info,
                "capture": {
                    "ok": True,
                    "rms": rms,
                    "peak": peak,
                    "heard_signal": True
                },
                "stt": {
                    "configured": False,
                    "provider": "vosk",
                    "transcript": None,
                    "error_type": "STT_NOT_CONFIGURED",
                    "fix": f"Модель Vosk не найдена. Распакуйте модель в папку: {model_path}"
                },
                "assistant_result": None,
            }

        # 5. Transcribe
        stt_result = self.stt.transcribe(capture)
        transcript = stt_result.get("transcript")

        # 6. Handle empty transcript
        if not transcript:
            return {
                "ok": False,
                "transcript": None,
                "final_status": "empty_transcript",
                "device": device_info,
                "capture": {
                    "ok": True,
                    "rms": rms,
                    "peak": peak,
                    "heard_signal": True
                },
                "stt": {
                    "configured": True,
                    "provider": "vosk",
                    "transcript": None,
                    "error_type": "EMPTY_TRANSCRIPT",
                    "fix": "Речь не распознана. Попробуйте говорить ближе к микрофону и чётче."
                },
                "assistant_result": None,
            }

        # 7. Query Assistant
        assistant_result = None
        if send_to_assistant:
            from app.core.assistant_orchestrator import AssistantOrchestrator
            import asyncio
            import concurrent.futures

            async def run_ask():
                return await AssistantOrchestrator(self.settings).ask(
                    str(transcript),
                    speak=True,
                    source="voice",
                    context={"dry_run": dry_run},
                )

            try:
                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: asyncio.run(run_ask()))
                    assistant_result = future.result()
            except RuntimeError:
                assistant_result = asyncio.run(run_ask())

        return {
            "ok": True,
            "transcript": transcript,
            "final_status": "sent_to_assistant" if send_to_assistant else "recorded",
            "device": device_info,
            "capture": {
                "ok": True,
                "rms": rms,
                "peak": peak,
                "heard_signal": True
            },
            "stt": {
                "configured": True,
                "provider": "vosk",
                "transcript": transcript,
                "error_type": None,
                "fix": None
            },
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
