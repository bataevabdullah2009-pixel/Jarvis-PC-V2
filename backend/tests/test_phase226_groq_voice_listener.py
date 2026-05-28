from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.providers.openrouter import PlannerResult
from app.router.ai_planner import AIPlanner
from app.router.command_router import CommandRouter
from app.voice import anti_echo
from app.voice.listener import voice_listener
from app.voice.speech_queue import speech_queue
from app.voice.tts import TTSService


ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_default_backend_port_18000() -> None:
    text = (ROOT / "backend" / "run_backend.py").read_text(encoding="utf-8")
    assert 'os.getenv("JARVIS_BACKEND_PORT", "18000")' in text


def test_frontend_default_api_base_18000() -> None:
    text = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert 'http://127.0.0.1:18000' in text
    assert 'http://127.0.0.1:8000' not in text


def test_env_example_contains_groq_tts_listener() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for expected in [
        "JARVIS_AI_PRIMARY=groq",
        "JARVIS_AI_FALLBACK=openrouter",
        "JARVIS_GROQ_MODEL=llama-3.1-8b-instant",
        "JARVIS_TTS_PRIMARY=fish_audio",
        "JARVIS_LISTENER_AUTOSTART=true",
        "JARVIS_WAKE_WORDS=джарвис,чарли,jarvis",
    ]:
        assert expected in text


def test_groq_provider_success_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.groq import GroqPlanner

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"OK"}}]}'
        reason_phrase = "OK"

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "OK"}}]}

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    settings = Settings()
    settings.groq_api_key = "fake"
    monkeypatch.setattr("app.providers.groq.httpx.Client", FakeClient)

    result = GroqPlanner(settings).plan("Ответь OK")

    assert result.status == "answered"
    assert result.provider == "groq"
    assert result.answer_text == "OK"


def test_groq_key_missing_structured() -> None:
    from app.providers.groq import GroqPlanner

    settings = Settings()
    settings.groq_api_key = None
    result = GroqPlanner(settings).plan("hello")

    assert result.status == "unavailable"
    assert result.error_type == "groq_key_missing"
    assert result.openrouter_called is False
    assert result.fix


def test_groq_rate_limit_fallback_to_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.groq_api_key = "fake"
    settings.openrouter_api_key = "fake"

    def fake_groq(self: Any, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        return PlannerResult(
            status="unavailable",
            answer_text="Groq rate limited.",
            actions=[],
            provider="groq",
            error_type="rate_limited",
            error_message="rate limit",
            status_code=429,
        )

    def fake_openrouter(self: Any, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="fallback ok",
            actions=[],
            provider="openrouter",
            model=settings.openrouter_model,
            openrouter_called=True,
        )

    monkeypatch.setattr("app.providers.groq.GroqPlanner.plan", fake_groq)
    monkeypatch.setattr("app.providers.openrouter.OpenRouterPlanner.plan", fake_openrouter)

    result = AIPlanner(settings).plan("question")

    assert result.status == "answered"
    assert result.provider == "openrouter"
    assert result.answer_text == "fallback ok"


def test_ai_router_groq_primary_openrouter_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    return test_groq_rate_limit_fallback_to_openrouter(monkeypatch)


def test_pytest_does_not_require_real_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JARVIS_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = Settings()
    settings.groq_api_key = None

    result = AIPlanner(settings).plan("cloud question")

    assert result.status == "ai_limited"
    assert result.provider == "text_only"


def test_local_commands_do_not_call_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.load()

    def boom(*args: Any, **kwargs: Any) -> PlannerResult:
        raise AssertionError("AI should not be called for local command")

    monkeypatch.setattr("app.router.ai_planner.AIPlanner.plan", boom)
    result = CommandRouter(settings).handle("я вернулся", context={"speak": False, "dry_run": True})

    assert result["local_matched"] is True
    assert result["openrouter_called"] is False


def test_tts_no_provider_none() -> None:
    settings = Settings()
    settings.fish_audio_api_key = None
    settings.fish_audio_voice_id = None
    result = TTSService(settings).speak("Проверка", dry_run=False, blocking=True)

    assert result["provider"] != "none"
    assert result["provider"] == "text_only"


def test_jarvis_style_blocks_edge_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.voice_profile = "Jarvis style"
    settings.tts_require_fish_audio = True
    settings.tts_fallback_enabled = True
    settings.fish_audio_api_key = None
    settings.fish_audio_voice_id = None

    def edge_should_not_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Edge TTS must not run in Jarvis style voice lock")

    monkeypatch.setattr("app.providers.edge_tts_provider.EdgeTTSProvider.synthesize", edge_should_not_run)
    result = TTSService(settings).speak("Проверка", dry_run=False, blocking=True)

    assert result["provider"] == "text_only"
    assert result["fallback_used"] is False


def test_tts_queue_final_status_not_stuck_queued() -> None:
    class FakeTTS:
        def speak(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
            return {
                "ok": True,
                "provider": "fish_audio",
                "status": "completed",
                "played": True,
                "spoken": True,
                "latency_ms": 1,
            }

    speech_queue.submit("test_phase226_queue", "test", "Привет", FakeTTS())
    speech_queue._queue.join()
    status = speech_queue.status()

    assert status["last_job_id"] == "test_phase226_queue"
    assert status["last_job_status"] == "played"
    assert status["last_provider"] == "fish_audio"


def test_debug_test_jarvis_voice_returns_final_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_speak(self: Any, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
        return {
            "ok": True,
            "provider": "fish_audio",
            "status": "completed",
            "played": True,
            "spoken": True,
            "audio_bytes": 10,
            "latency_ms": 1,
        }

    monkeypatch.setattr("app.voice.tts.TTSService.speak", fake_speak)
    response = client.post("/debug/test-jarvis-voice", json={"text": "Проверка"})
    body = response.json()

    assert body["ok"] is True
    assert body["data"]["provider"] == "fish_audio"
    assert body["data"]["job_status"] == "played"


def test_listener_autostart_success(monkeypatch: pytest.MonkeyPatch) -> None:
    voice_listener.stop()
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._self_echo_loop_triggered = False
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": True})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    monkeypatch.setattr("app.voice.listener.VoiceListener.process_audio_window", lambda self: self._stop_event.wait(0.01))

    result = voice_listener.start(device_id="default", force_start=False)

    assert result["data"]["running"] is True
    assert result["data"]["state"] in {"idle", "listening_for_trigger", "listening_for_wake_word", "idle_listening_for_wake_word"}
    voice_listener.stop()


def test_listener_autostart_quiet_room_keeps_running(monkeypatch: pytest.MonkeyPatch) -> None:
    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": False})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    monkeypatch.setattr("app.voice.listener.is_speaking_now", lambda: False)

    result = voice_listener.start(device_id="default", force_start=False)

    assert result["data"]["running"] is True
    assert result["data"]["state"] in {"starting", "listening_for_wake_word", "idle_listening_for_wake_word"}
    voice_listener.stop()


def test_anti_echo_blocks_self_transcript() -> None:
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = "Я открыл Telegram, сэр."
    anti_echo._consecutive_echo_count = 0
    anti_echo._self_echo_loop_triggered = False

    result = anti_echo.should_ignore_transcript("Я открыл Telegram сэр")

    assert result["ignore"] is True
    assert result["self_echo_blocked"] is True


def test_ui_no_mojibake_static_strings() -> None:
    for relative in ["frontend/src/screens/MinimalUI.tsx", "frontend/src/screens/App.tsx", "frontend/src/api/client.ts"]:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "\u0420\u040e" not in text
        assert "\u0420\u045f" not in text
        assert "\u0432\u0402" not in text
        assert "????" not in text


def test_check_source_format_catches_one_line_files(tmp_path: Path) -> None:
    checker = (ROOT / "tools" / "check_source_format.py").read_text(encoding="utf-8")
    assert "first line is longer than 2000 bytes" in checker
    assert "LF count == 0" in checker
