from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.voice import anti_echo
from app.voice.listener import voice_listener
from app.voice.tts import TTSService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_no_provider_none_in_tts_response(monkeypatch) -> None:
    def fake_say(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict:
        return {
            "ok": False,
            "provider": "none",
            "spoken": False,
            "played": False,
            "fallback_used": False,
            "error": "simulated",
            "error_type": "fish_api_error",
            "fix": "fix",
        }

    monkeypatch.setattr("app.voice.speech_orchestrator.SpeechOrchestrator.say", fake_say)
    body = client.post("/voice/say", json={"text": "Проверка"}).json()
    assert body["data"]["provider"] != "none"
    assert body["provider"] != "none"


def test_jarvis_style_blocks_edge_tts(monkeypatch) -> None:
    settings = Settings()
    settings.voice_profile = "Jarvis style"
    settings.tts_require_fish_audio = True
    settings.tts_fallback_enabled = False
    settings.fish_audio_api_key = None
    settings.fish_audio_voice_id = None

    edge_called = False
    offline_called = False

    def fake_edge(self) -> bool:
        nonlocal edge_called
        edge_called = True
        return True

    def fake_offline(self) -> bool:
        nonlocal offline_called
        offline_called = True
        return True

    monkeypatch.setattr("app.providers.edge_tts_provider.EdgeTTSProvider.available", fake_edge)
    monkeypatch.setattr("app.providers.offline_tts.OfflineTTS.available", fake_offline)

    result = TTSService(settings).speak("Проверка", dry_run=True)
    assert result["provider"] == "text_only"
    assert result["error_type"] == "fish_key_missing"
    assert edge_called is False
    assert offline_called is False


def test_fish_config_visible_in_voice_provider_status(monkeypatch) -> None:
    settings = Settings()
    settings.fish_audio_api_key = "fish_key"
    settings.fish_audio_voice_id = "fish_voice"
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    body = client.get("/debug/voice-provider-status").json()
    assert body["ok"] is True
    assert body["data"]["fish_key_present"] is True
    assert body["data"]["fish_voice_id_present"] is True
    assert body["data"]["selected_provider"] == "fish_audio"


def test_listener_autostart_enabled_but_blocked_no_audio(monkeypatch) -> None:
    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": False})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})

    result = voice_listener.start(device_id="default")
    data = result["data"]
    assert result["ok"] is False
    assert data["state"] == "blocked"
    assert data["running"] is False
    assert data["last_error_type"] == "microphone_no_audio"


def test_listener_autostart_enabled_success(monkeypatch) -> None:
    voice_listener.stop()
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda device_id="default": {"ok": True, "device_name": "Test Mic"})
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id="default", duration_seconds=0.2: {"heard_signal": True})
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    monkeypatch.setattr("app.voice.listener.VoiceListener.process_audio_window", lambda self: self._stop_event.wait(0.05))

    result = voice_listener.start(device_id="default")
    data = result["data"]
    assert data["running"] is True
    assert data["state"] in {"idle", "listening_for_trigger"}
    voice_listener.stop()


def test_anti_echo_blocks_self_transcript() -> None:
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = "Я открыл Telegram, сэр."
    anti_echo._consecutive_echo_count = 0
    anti_echo._self_echo_loop_triggered = False

    assistant = MagicMock()
    result = anti_echo.should_ignore_transcript("Я открыл Telegram сэр")
    if not result["ignore"]:
        assistant()

    assert result["ignore"] is True
    assert result["self_echo_blocked"] is True
    assistant.assert_not_called()


def test_ui_does_not_show_mojibake() -> None:
    text = (PROJECT_ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    for marker in ("Рџ", "РЅ", "Ð"):
        assert marker not in text


def test_start_jarvis_line_endings() -> None:
    path = PROJECT_ROOT / "START_JARVIS.bat"
    assert len(path.read_text(encoding="utf-8").splitlines()) >= 4
    assert path.read_bytes().count(b"\r\n") >= 4


def test_client_ts_not_one_line() -> None:
    assert len((PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8").splitlines()) >= 150


def test_check_source_format_catches_one_line_files(tmp_path) -> None:
    files = {
        PROJECT_ROOT / "START_JARVIS.bat": b"@echo off\r\n",
        PROJECT_ROOT / "tools" / "start_jarvis.ps1": b"Write-Host 'bad'\r\n",
        PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts": b"export const bad = true;\n",
    }
    originals = {path: path.read_bytes() for path in files}
    try:
        for path, content in files.items():
            path.write_bytes(content)
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "check_source_format.py")],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "START_JARVIS.bat" in result.stdout
        assert "tools/start_jarvis.ps1" in result.stdout
        assert "frontend/src/api/client.ts" in result.stdout
    finally:
        for path, content in originals.items():
            path.write_bytes(content)
