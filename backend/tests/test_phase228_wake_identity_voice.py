from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import CONFIG_DIR, Settings, patch_settings
from app.main import app
from app.providers.fish_audio import FishAudioTTS
from app.voice import anti_echo
from app.voice.speech_queue import speech_queue
from app.voice.wakeword import extract_wake_command


ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _with_settings_restore(fn):
    settings_path = CONFIG_DIR / "settings.json"
    original = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    try:
        return fn()
    finally:
        if original is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_text(original, encoding="utf-8", newline="\n")


def test_files_are_not_one_line() -> None:
    required = {
        "START_JARVIS.bat": 4,
        "tools/start_jarvis.ps1": 80,
        "tools/check_source_format.py": 120,
        "backend/run_backend.py": 10,
        "backend/app/main.py": 300,
        "frontend/src/api/client.ts": 150,
        "frontend/src/screens/MinimalUI.tsx": 300,
        ".env.example": 60,
        "README.md": 50,
    }
    for relative, minimum in required.items():
        lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
        assert len(lines) >= minimum, relative
        assert len(lines[0]) < 2000, relative


def test_backend_port_18000() -> None:
    text = (ROOT / "backend" / "run_backend.py").read_text(encoding="utf-8")
    assert '"18000"' in text
    assert '"8000"' not in text


def test_settings_assistant_identity_fields() -> None:
    data = client.get("/settings").json()["data"]
    for key in ["assistant_name", "assistant_display_name", "assistant_address_style", "wake_words"]:
        assert key in data


def test_patch_settings_persists_assistant_name() -> None:
    def run() -> None:
        updated = patch_settings({"assistant_name": "Чарли"})
        assert updated.assistant_name == "Чарли"
    _with_settings_restore(run)


def test_patch_settings_persists_wake_words() -> None:
    def run() -> None:
        updated = patch_settings({"wake_words": "альфа, бета"})
        assert updated.wake_words == ["альфа", "бета"]
    _with_settings_restore(run)


def test_wakeword_extracts_command() -> None:
    result = extract_wake_command("эй джарвис открой браузер", ["джарвис", "чарли", "jarvis"])
    assert result["triggered"] is True
    assert result["wake_word"] == "джарвис"
    assert result["command_text"] == "открой браузер"


def test_no_wake_word_is_ignored() -> None:
    result = extract_wake_command("как дела", ["джарвис"])
    assert result == {"triggered": False, "wake_word": None, "command_text": "", "reason": "no_wake_word"}


def test_empty_wake_word_returns_yes_sir() -> None:
    result = extract_wake_command("джарвис", ["джарвис"])
    assert result["triggered"] is True
    assert result["command_text"] == ""
    assert result["reason"] == "empty_command"


def test_listener_autostart_enabled_by_default() -> None:
    settings = Settings()
    assert settings.listener_enabled is True
    assert settings.listener_autostart is True


def test_listener_status_has_reason_if_not_running(monkeypatch) -> None:
    from app.voice.listener import voice_listener

    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": False})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    data = voice_listener.status()["data"]
    assert data["state"] == "blocked"
    assert data["last_error_type"]
    assert data["fix"]


def test_listener_uses_wake_words_from_settings(monkeypatch) -> None:
    from app.voice.listener import voice_listener

    def run() -> None:
        patch_settings({"wake_words": ["альфа"]})
        capture = type("Capture", (), {"rms": 0.1, "peak": 0.1})()
        monkeypatch.setattr("app.voice.listener.STTService", lambda settings: type("STT", (), {"transcribe": lambda self, cap: {"transcript": "альфа статус"}})())
        monkeypatch.setattr("app.voice.listener.should_ignore_transcript", lambda text: {"ignore": False, "reason": None, "self_echo_blocked": False, "stop_listener": False, "fix": None})
        monkeypatch.setattr(voice_listener, "send_to_assistant", lambda text: setattr(voice_listener, "last_command_text", text))
        voice_listener.detect_trigger(capture)
        assert voice_listener.last_command_text == "статус"
    _with_settings_restore(run)


def test_voice_profiles_schema() -> None:
    data = client.get("/settings").json()["data"]
    assert data["voice_profile_id"]
    assert isinstance(data["voice_profiles"], list)
    assert {"id", "name", "provider", "voice_id", "tone", "enabled"}.issubset(data["voice_profiles"][0])


def test_patch_settings_persists_voice_profile_id() -> None:
    def run() -> None:
        updated = patch_settings({"voice_profile_id": "jarvis_deep"})
        assert updated.voice_profile_id == "jarvis_deep"
    _with_settings_restore(run)


def test_selected_fish_voice_id_used_for_tts() -> None:
    settings = Settings()
    settings.fish_audio_api_key = "key"
    settings.voice_profile_id = "jarvis_deep"
    settings.voice_profiles = [
        {"id": "jarvis_main", "name": "Main", "provider": "fish_audio", "voice_id": "voice_one", "tone": "calm", "enabled": True},
        {"id": "jarvis_deep", "name": "Deep", "provider": "fish_audio", "voice_id": "voice_two", "tone": "serious", "enabled": True},
    ]
    FishAudioTTS(settings)
    assert settings.fish_audio_voice_id == "voice_two"


def test_missing_voice_id_returns_text_only_not_none() -> None:
    settings = Settings()
    settings.fish_audio_api_key = "key"
    settings.fish_audio_voice_id = None
    from app.voice.tts import TTSService

    result = TTSService(settings).speak("Проверка", blocking=True)
    assert result["provider"] == "text_only"
    assert result["error_type"] == "fish_voice_id_missing"


def test_tts_job_reaches_final_status() -> None:
    class FakeTTS:
        def speak(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
            return {"ok": True, "provider": "fish_audio", "status": "completed", "played": True, "spoken": True}

    speech_queue.submit("phase228_final", "test", "hello", FakeTTS())
    speech_queue._queue.join()
    assert speech_queue.status()["last_job_status"] in {"played", "text_only", "failed", "cancelled"}


def test_tts_status_not_stuck_queued() -> None:
    data = client.get("/voice/tts-status").json()["data"]
    assert data["last_job_status"] != "queued" or data.get("last_job_age_seconds", 0) <= 10


def test_tts_reset_clears_stuck_jobs() -> None:
    data = client.post("/voice/tts-reset").json()["data"]
    assert data["queue_size"] == 0
    assert data["last_job_status"] == "failed"


def test_anti_echo_blocks_self_transcript() -> None:
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = "Я открыл браузер, сэр."
    anti_echo._consecutive_echo_count = 0
    result = anti_echo.should_ignore_transcript("я открыл браузер сэр")
    assert result["ignore"] is True


def test_local_voice_status_endpoint_shape() -> None:
    data = client.get("/debug/local-voice-status").json()["data"]
    for key in ["fish_audio", "piper_local", "xtts_local", "gpt_sovits_local", "rvc_converter"]:
        assert key in data


def test_ui_has_assistant_identity_panel() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "Личность ассистента" in text
    assert "Сохранить личность" in text


def test_ui_has_voice_profiles_panel() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "Голоса" in text
    assert "Сохранить голос" in text
    assert "Автослушание 24/7" in text


def test_ui_listener_status_not_unknown_reason() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "Live listener не стартовал: неизвестная причина" not in text


def test_ui_no_mojibake() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    for marker in ["Рџ", "РЎ", "Рґ", "СЃ", "вЂ"]:
        assert marker not in text
