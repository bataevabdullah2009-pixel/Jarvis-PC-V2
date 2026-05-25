from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import CONFIG_DIR, Settings, get_settings, patch_settings
from app.main import app
from app.providers.openrouter import PlannerResult
from app.router.ai_planner import AIPlanner
from app.voice import anti_echo
from app.voice.speech_queue import speech_queue
from app.voice.tts import TTSService


ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_source_files_are_not_one_line() -> None:
    for relative in [
        "START_JARVIS.bat",
        "tools/start_jarvis.ps1",
        "backend/app/core/config.py",
        "frontend/src/api/client.ts",
        "frontend/src/screens/MinimalUI.tsx",
        ".env.example",
        "README.md",
    ]:
        lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 4, relative
        assert len(lines[0]) < 2000, relative


def test_default_backend_port_is_18000() -> None:
    text = (ROOT / "backend" / "run_backend.py").read_text(encoding="utf-8")
    assert 'os.getenv("JARVIS_BACKEND_PORT", "18000")' in text


def test_frontend_api_base_default_18000() -> None:
    text = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert 'http://127.0.0.1:18000' in text
    assert "127.0.0.1:8000" not in text


def test_settings_patch_persists_ai_provider(monkeypatch) -> None:
    settings_path = CONFIG_DIR / "settings.json"
    original = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    monkeypatch.delenv("JARVIS_AI_PRIMARY", raising=False)
    monkeypatch.delenv("JARVIS_AI_FALLBACK", raising=False)
    try:
        updated = patch_settings({"ai_primary": "openrouter", "ai_fallback": "groq"})
        assert updated.ai_primary == "openrouter"
        assert updated.ai_fallback == "groq"
        assert get_settings().ai_primary == "openrouter"
        assert '"ai_primary": "openrouter"' in settings_path.read_text(encoding="utf-8")
    finally:
        if original is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_text(original, encoding="utf-8", newline="\n")


def test_ai_provider_dropdown_fields_exist_in_settings_schema() -> None:
    data = client.get("/settings").json()["data"]
    for field in ["ai_primary", "ai_fallback", "ai_allow_local_fallback", "groq_configured", "openrouter_configured"]:
        assert field in data


def test_groq_forbidden_falls_back_to_openrouter(monkeypatch) -> None:
    settings = Settings()
    settings.groq_api_key = "fake"
    settings.openrouter_api_key = "fake"

    def fake_groq(self: Any, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        return PlannerResult(status="unavailable", answer_text="", actions=[], provider="groq", status_code=403, error_type="groq_forbidden")

    def fake_openrouter(self: Any, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        return PlannerResult(status="answered", answer_text="fallback ok", actions=[], provider="openrouter", openrouter_called=True)

    monkeypatch.setattr("app.providers.groq.GroqPlanner.plan", fake_groq)
    monkeypatch.setattr("app.providers.openrouter.OpenRouterPlanner.plan", fake_openrouter)
    result = AIPlanner(settings).plan("question")
    assert result.provider == "openrouter"
    assert result.answer_text == "fallback ok"


def test_tts_job_reaches_final_status() -> None:
    class FakeTTS:
        def speak(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
            return {"ok": True, "provider": "fish_audio", "status": "completed", "played": True, "spoken": True}

    speech_queue.submit("phase227_final", "test", "hello", FakeTTS())
    speech_queue._queue.join()
    assert speech_queue.status()["last_job_status"] == "played"


def test_tts_status_not_stuck_queued() -> None:
    status = client.get("/voice/tts-status").json()["data"]
    assert status["last_job_status"] != "queued" or status.get("last_job_age_seconds", 0) <= 10


def test_debug_test_jarvis_voice_returns_played_or_failed(monkeypatch) -> None:
    monkeypatch.setattr(TTSService, "speak", lambda self, text, dry_run=False, blocking=False: {"ok": False, "provider": "text_only", "played": False, "error_type": "fish_key_missing", "error": "missing"})
    data = client.post("/debug/test-jarvis-voice", json={"text": "Проверка"}).json()["data"]
    assert data["job_status"] in {"played", "failed"}
    assert data["provider"] != "none"


def test_no_provider_none_in_tts() -> None:
    result = TTSService(Settings()).speak("Проверка", blocking=True)
    assert result["provider"] != "none"


def test_jarvis_style_blocks_edge_tts(monkeypatch) -> None:
    settings = Settings()
    settings.voice_profile = "Jarvis style"
    settings.tts_require_fish_audio = True
    settings.tts_fallback_enabled = True
    monkeypatch.setattr("app.providers.edge_tts_provider.EdgeTTSProvider.synthesize", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("edge blocked")))
    assert TTSService(settings).speak("Проверка", blocking=True)["provider"] == "text_only"


def test_listener_autostart_enabled_by_default() -> None:
    settings = Settings()
    assert settings.listener_enabled is True
    assert settings.listener_autostart is True


def test_listener_status_not_disabled_when_enabled_but_blocked(monkeypatch) -> None:
    from app.voice.listener import voice_listener

    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": False})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    data = voice_listener.status()["data"]
    assert data["enabled"] is True
    assert data["state"] == "blocked"


def test_listener_blocked_has_reason_and_fix(monkeypatch) -> None:
    from app.voice.listener import voice_listener

    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": False})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    data = voice_listener.status()["data"]
    assert data["last_error_type"] == "microphone_no_audio"
    assert data["fix"]


def test_microphone_calibration_returns_rms_peak_heard_signal(monkeypatch) -> None:
    class Capture:
        def __init__(self, rms: float, peak: float) -> None:
            self.rms = rms
            self.peak = peak

    calls = iter([Capture(0.001, 0.002), Capture(0.02, 0.1)])
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.microphone.capture_audio", lambda **kwargs: next(calls))
    body = client.post("/voice/calibrate-mic", json={"device_id": "default"}).json()
    assert body["ok"] is True
    assert body["data"]["heard_signal"] is True
    assert body["data"]["speech_peak"] == 0.1


def test_anti_echo_blocks_self_transcript() -> None:
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = "Я открыл Telegram, сэр."
    anti_echo._consecutive_echo_count = 0
    result = anti_echo.should_ignore_transcript("Я открыл Telegram сэр")
    assert result["ignore"] is True


def test_ui_provider_selection_refreshes_settings() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "App.tsx").read_text(encoding="utf-8")
    assert "api.patchSettings(patch)" in text
    assert "api.settings()" in text
    assert "api.aiProviderStatus()" in text
    assert "Backend вернул другое значение AI provider" in text


def test_ui_no_mojibake() -> None:
    for relative in ["frontend/src/screens/MinimalUI.tsx", "frontend/src/screens/App.tsx", "frontend/src/api/client.ts"]:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for marker in ["Рџ", "Рћ", "РЅ", "СЃ", "СЊ", "С‹", "вЂ"]:
            assert marker not in text
