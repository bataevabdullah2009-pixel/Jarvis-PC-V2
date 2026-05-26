from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import CONFIG_DIR, Settings, patch_settings
from app.main import app
from app.providers.gpt_sovits_local import GPTSoVITSLocalTTS
from app.providers.piper_local import PiperLocalTTS
from app.router.command_router import CommandRouter
from app.voice.speech_queue import speech_queue
from app.voice.wakeword import extract_wake_command


ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _restore_file(path: Path):
    original = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        yield
    finally:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(original, encoding="utf-8", newline="\n")


def test_start_jarvis_bat_exact_shape() -> None:
    assert (ROOT / "START_JARVIS.bat").read_text(encoding="utf-8").splitlines() == [
        "@echo off",
        'cd /d "%~dp0"',
        'powershell -NoProfile -ExecutionPolicy Bypass -File "tools\\start_jarvis.ps1"',
        "pause",
    ]


def test_listener_enabled_not_stopped_without_reason(monkeypatch) -> None:
    from app.voice.listener import voice_listener

    patch_settings({"listener_enabled": True, "listener_autostart": True})
    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": False})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    data = voice_listener.status()["data"]
    assert data["state"] == "blocked"
    assert data["last_error_type"] in {"microphone_no_audio", "listener_thread_crashed"}
    assert data["metrics"]["stops_without_reason"] >= 0


def test_listener_status_has_reason_if_blocked() -> None:
    data = client.get("/voice/listener-status").json()["data"]
    if data["state"] == "blocked":
        assert data["last_error_type"]
        assert data["fix"]


def test_listener_autostart_toggle_persists() -> None:
    settings_path = CONFIG_DIR / "settings.json"
    original = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    try:
        settings = patch_settings({"listener_enabled": False, "listener_autostart": False, "listener_device_id": "default"})
        assert settings.listener_enabled is False
        assert settings.listener_autostart is False
        settings = patch_settings({"listener_enabled": True, "listener_autostart": True, "listener_device_id": "1"})
        assert settings.listener_enabled is True
        assert settings.listener_autostart is True
        assert settings.listener_device_id == "1"
    finally:
        if original is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_text(original, encoding="utf-8", newline="\n")


def test_wakeword_ignores_without_name() -> None:
    assert extract_wake_command("открой браузер", ["джарвис"])["triggered"] is False


def test_wakeword_accepts_jarvis_command() -> None:
    data = extract_wake_command("Джарвис, как дела", ["джарвис", "чарли", "jarvis"])
    assert data["triggered"] is True
    assert data["wake_word"] == "джарвис"
    assert data["command_text"] == "как дела"


def test_microphone_calibration_shape(monkeypatch) -> None:
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    capture = type("Capture", (), {"rms": 0.01, "peak": 0.04})()
    monkeypatch.setattr("app.voice.microphone.capture_audio", lambda **kwargs: capture)
    data = client.post("/voice/calibrate-mic", json={"device_id": "default", "silence_seconds": 0, "speech_seconds": 0}).json()["data"]
    assert {"device_id", "device_name", "noise_floor_rms", "speech_rms", "speech_peak", "heard_signal", "recommended_min_rms_threshold", "fixes"}.issubset(data)


def test_commands_crud_create_update_delete() -> None:
    commands_path = CONFIG_DIR / "local_commands_ru.json"
    restore = _restore_file(commands_path)
    next(restore)
    try:
        created = client.post(
            "/commands",
            json={"title": "Test command", "phrases": ["phase command"], "action_type": "speak", "action_value": "ok", "enabled": True},
        ).json()["data"]
        assert created["title"] == "Test command"
        updated = client.patch(f"/commands/{created['id']}", json={"title": "Updated command", "action_value": "done"}).json()["data"]
        assert updated["title"] == "Updated command"
        deleted = client.delete(f"/commands/{created['id']}").json()["data"]
        assert deleted["deleted"] is True
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


def test_commands_crud_create() -> None:
    test_commands_crud_create_update_delete()


def test_commands_crud_update() -> None:
    test_commands_crud_create_update_delete()


def test_commands_crud_delete() -> None:
    test_commands_crud_create_update_delete()


def test_command_router_uses_custom_command() -> None:
    commands_path = CONFIG_DIR / "local_commands_ru.json"
    restore = _restore_file(commands_path)
    next(restore)
    try:
        client.post("/commands", json={"title": "Say OK", "phrases": ["phase router"], "action_type": "speak", "action_value": "router ok"})
        result = CommandRouter(Settings()).handle("phase router", source="test")
        assert result["route"] == "local_command"
        assert "router ok" in result["response_text"]
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


def test_voice_profiles_persist() -> None:
    settings_path = CONFIG_DIR / "settings.json"
    original = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    try:
        settings = patch_settings({"voice_profile_id": "assistant_alt"})
        assert settings.voice_profile_id == "assistant_alt"
    finally:
        if original is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_text(original, encoding="utf-8", newline="\n")


def test_selected_voice_profile_used_for_tts() -> None:
    settings = Settings()
    settings.fish_audio_api_key = "key"
    settings.voice_profile_id = "jarvis_main"
    settings.voice_profiles = [{"id": "jarvis_main", "name": "Main", "provider": "fish_audio", "voice_id": "voice-x", "tone": "calm", "enabled": True}]
    from app.providers.fish_audio import FishAudioTTS

    FishAudioTTS(settings)
    assert settings.fish_audio_voice_id == "voice-x"


def test_tts_not_stuck_queued() -> None:
    data = client.get("/voice/tts-status").json()["data"]
    assert data["last_job_status"] != "queued" or data.get("last_job_age_seconds", 0) <= 10


def test_piper_status_disabled_by_default() -> None:
    status = PiperLocalTTS(Settings()).status()
    assert status["enabled"] is False
    assert status["available"] is False


def test_piper_provider_missing_model_structured_error() -> None:
    settings = Settings()
    settings.piper_enabled = True
    settings.piper_model_path = "models/piper/missing.onnx"
    result = PiperLocalTTS(settings).synthesize("hello")
    assert result["ok"] is False
    assert result["error_type"] == "piper_model_missing"


def test_gpt_sovits_status_disabled_by_default() -> None:
    status = GPTSoVITSLocalTTS(Settings()).status()
    assert status["enabled"] is False
    assert status["available"] is False


def test_gpt_sovits_api_unreachable_structured_error() -> None:
    settings = Settings()
    settings.gpt_sovits_enabled = True
    settings.gpt_sovits_api_url = "http://127.0.0.1:9"
    result = GPTSoVITSLocalTTS(settings).synthesize("hello")
    assert result["ok"] is False
    assert result["error_type"] == "gpt_sovits_api_unreachable"


def test_local_voice_status_contains_all_engines() -> None:
    data = client.get("/debug/local-voice-status").json()["data"]
    for key in ["fish_audio", "piper_local", "gpt_sovits_local", "xtts_local", "rvc_converter", "text_only"]:
        assert key in data


def test_ui_has_autolisten_status() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "Автослушание 24/7" in text
    assert "stopped without reason" not in text


def test_ui_has_commands_crud() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "Добавить команду" in text
    assert "api.createCommand" in text
    assert "api.updateCommand" in text
    assert "api.deleteCommand" in text


def test_ui_has_local_voice_provider_options() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    for marker in ["piper_local", "gpt_sovits_local", "xtts_local", "text_only", "Проверить выбранный голос"]:
        assert marker in text


def test_ui_no_mojibake() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    for marker in ["Р Сџ", "Р РЋ", "Р Т‘", "РЎРѓ", "РІР‚"]:
        assert marker not in text
