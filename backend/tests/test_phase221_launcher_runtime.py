from __future__ import annotations

import os
from fastapi.testclient import TestClient
from app.main import app
from app.voice.listener import voice_listener
from app.features.reminders import reminder_service

client = TestClient(app)


def test_backend_import_has_no_side_effect_listener() -> None:
    # Verify listener thread is not running on import (since startup hasn't run in TestClient yet)
    assert voice_listener._thread is None or not voice_listener._thread.is_alive()
    assert voice_listener.state == "stopped"


def test_backend_import_has_no_immediate_reminder_tts() -> None:
    # Verify reminder service thread is not running on import
    assert reminder_service._thread is None or not reminder_service._thread.is_alive()
    assert reminder_service._running is False


def test_listener_status_contract_always_has_running() -> None:
    response = client.get("/voice/listener-status")
    assert response.status_code == 200
    body = response.json()
    assert "ok" in body
    assert "data" in body
    assert "running" in body["data"]
    assert "state" in body["data"]
    assert "device_id" in body["data"]
    assert "safe_to_start" in body["data"]
    assert "errors" in body["data"]
    assert "warnings" in body["data"]


def test_start_listener_contract_always_has_running(monkeypatch) -> None:
    # Even if safe gate fails, running should be present in the returned data dict!
    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda dev_id: {
        "ok": False,
        "error_type": "microphone_device_not_found",
        "fix": "Select another input device.",
    })
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id, duration_seconds: {
        "heard_signal": False, "rms": 0.0, "peak": 0.0
    })
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    monkeypatch.setattr("app.voice.listener.is_speaking_now", lambda: False)
    response = client.post(
        "/voice/start-listener",
        json={"wake_word": True, "clap": False, "device_id": "default"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "data" in body
    assert "running" in body["data"]
    assert body["data"]["running"] is False


def test_start_listener_allows_quiet_room(monkeypatch) -> None:
    # Force heard_signal = False
    voice_listener.stop()
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda dev_id: {
        "ok": True, "device_name": "Test Mic", "sample_rate": 16000, "channels": 1
    })
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id, duration_seconds: {
        "heard_signal": False, "rms": 0.0, "peak": 0.0
    })
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {"configured": True})
    monkeypatch.setattr("app.voice.listener.is_speaking_now", lambda: False)
    response = client.post(
        "/voice/start-listener",
        json={"wake_word": True, "clap": False, "device_id": "default"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["running"] is True
    assert body["data"]["state"] in {"starting", "listening_for_wake_word", "idle_listening_for_wake_word"}
    voice_listener.stop()


def test_assistant_ask_works_with_listener_disabled(monkeypatch) -> None:
    from app.providers.openrouter import PlannerResult
    from app.router.ai_planner import AIPlanner

    def fake_plan(self, text: str, context=None) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Mock OpenRouter OK",
            actions=[],
            provider="openrouter",
            openrouter_called=True,
            status_code=200,
        )

    monkeypatch.setattr(AIPlanner, "plan", fake_plan)
    # Even when voice listener is stopped, assistant/ask should work!
    voice_listener.stop()
    assert voice_listener.state == "stopped"
    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, как дела?",
            "speak": False,
            "source": "smoke",
            "context": {}
        }
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_commands_endpoint_available() -> None:
    response = client.get("/commands")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "commands" in body["data"]


def test_smoke_runtime_script_exists() -> None:
    test_dir = os.path.dirname(__file__)
    proj_root = os.path.abspath(os.path.join(test_dir, "..", ".."))
    script_path = os.path.join(proj_root, "tools", "smoke_runtime.ps1")
    assert os.path.exists(script_path)


def test_start_jarvis_launcher_exists() -> None:
    test_dir = os.path.dirname(__file__)
    proj_root = os.path.abspath(os.path.join(test_dir, "..", ".."))
    launcher_path = os.path.join(proj_root, "START_JARVIS.bat")
    assert os.path.exists(launcher_path)


def test_legacy_launchers_warn() -> None:
    test_dir = os.path.dirname(__file__)
    proj_root = os.path.abspath(os.path.join(test_dir, "..", ".."))
    
    dev_fresh = os.path.join(proj_root, "RUN_DEV_FRESH.bat")
    assert os.path.exists(dev_fresh)
    with open(dev_fresh, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    assert "START_JARVIS.bat" in content
    
    update_launch = os.path.join(proj_root, "UPDATE_AND_LAUNCH_APP.bat")
    assert os.path.exists(update_launch)
    with open(update_launch, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    assert "START_JARVIS.bat" in content
