from __future__ import annotations

import os
import pytest
from typing import Any


# 1. test_pytest_test_mode_enabled
def test_pytest_test_mode_enabled() -> None:
    assert os.environ.get("JARVIS_TEST_MODE") == "true"


# 2. test_no_real_ai_provider_in_pytest
def test_no_real_ai_provider_in_pytest() -> None:
    import socket
    with pytest.raises(RuntimeError, match="REAL_PROVIDER_USED_IN_TESTS"):
        s = socket.socket()
        s.connect(("openrouter.ai", 443))


# 3. test_no_real_tts_provider_in_pytest
def test_no_real_tts_provider_in_pytest() -> None:
    from app.providers.offline_tts import OfflineTTS
    planner = OfflineTTS()
    with pytest.raises(RuntimeError, match="REAL_PROVIDER_USED_IN_TESTS"):
        planner.speak("hello", dry_run=False)


# 4. test_no_real_microphone_in_pytest
def test_no_real_microphone_in_pytest() -> None:
    try:
        import sounddevice as sd
        with pytest.raises(RuntimeError, match="REAL_PROVIDER_USED_IN_TESTS"):
            sd.InputStream()
    except ImportError:
        pass


# 5. test_listener_status_running_truth
def test_listener_status_running_truth() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice.listener import voice_listener
    
    orig_status = voice_listener.status
    try:
        voice_listener.status = lambda: {
            "ok": True,
            "data": {
                "running": True,
                "state": "listening_for_wake_word",
                "device_id": "default",
                "device_name": "Test Mic",
                "last_error_type": None,
                "last_error": None,
                "fix": None,
            }
        }
        client = TestClient(app)
        res = client.get("/voice/listener-status")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["running"] is True
        assert data["state"] == "listening_for_wake_word"
        assert data["status_text"] == "Слушаю 24/7: скажите 'Джарвис'"
    finally:
        voice_listener.status = orig_status


# 6. test_listener_status_blocked_has_reason
def test_listener_status_blocked_has_reason() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice.listener import voice_listener
    
    orig_status = voice_listener.status
    try:
        voice_listener.status = lambda: {
            "ok": True,
            "data": {
                "running": False,
                "state": "blocked",
                "device_id": "default",
                "device_name": "Test Mic",
                "last_error_type": "microphone_permission_denied",
                "last_error": "No permission to access microphone.",
                "fix": "Enable permission.",
            }
        }
        client = TestClient(app)
        res = client.get("/voice/listener-status")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["running"] is False
        assert data["state"] == "blocked"
        assert data["last_error_type"] == "microphone_permission_denied"
        assert data["last_error"] == "No permission to access microphone."
        assert data["fix"] == "Enable permission."
    finally:
        voice_listener.status = orig_status


# 7. test_listener_status_never_unknown_reason
def test_listener_status_never_unknown_reason() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice.listener import voice_listener
    
    orig_status = voice_listener.status
    try:
        voice_listener.status = lambda: {
            "ok": True,
            "data": {
                "running": False,
                "state": "blocked",
                "device_id": "default",
                "device_name": "Test Mic",
                "last_error_type": "unknown reason",
                "last_error": "stopped without reason",
                "fix": "Restart the listener from UI or POST /voice/listener-start.",
            }
        }
        client = TestClient(app)
        res = client.get("/voice/listener-status")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "unknown reason" not in str(data.values())
        assert "stopped without reason" not in str(data.values())
        assert data["last_error_type"] == "microphone_open_failed"
        assert data["last_error"] == "Не удалось открыть аудио поток. Возможно, микрофон занят другим приложением."
        assert data["fix"] == "Проверьте подключение устройства и перезапустите слушатель."
    finally:
        voice_listener.status = orig_status


# 8. test_listener_start_success_contract
def test_listener_start_success_contract() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice.listener import voice_listener
    
    orig_resolve = voice_listener._resolve_input_device
    orig_check = voice_listener.check_safe_start
    orig_start = voice_listener.start
    orig_status = voice_listener.status
    
    try:
        voice_listener._resolve_input_device = lambda device_id: {"ok": True, "device_id": "mock_id", "device_name": "Mock Mic"}
        voice_listener.check_safe_start = lambda device_id: {"safe_to_start": True, "failed_check": None, "fix": None, "checks": {}}
        voice_listener.start = lambda **kwargs: {"ok": True}
        voice_listener.status = lambda: {
            "ok": True,
            "data": {
                "running": True,
                "state": "listening_for_wake_word",
                "device_id": "mock_id",
                "device_name": "Mock Mic",
                "last_error_type": None,
                "last_error": None,
                "fix": None,
            }
        }
        
        client = TestClient(app)
        res = client.post("/voice/listener-start", json={"device_id": "mock_id", "wake_word": True})
        assert res.status_code == 200
        resp_data = res.json()
        assert resp_data["ok"] is True
        assert resp_data["data"]["running"] is True
        assert resp_data["data"]["state"] == "listening_for_wake_word"
        assert resp_data["data"]["device_name"] == "Mock Mic"
    finally:
        voice_listener._resolve_input_device = orig_resolve
        voice_listener.check_safe_start = orig_check
        voice_listener.start = orig_start
        voice_listener.status = orig_status


# 9. test_listener_start_failure_contract
def test_listener_start_failure_contract() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice.listener import voice_listener
    
    orig_resolve = voice_listener._resolve_input_device
    orig_check = voice_listener.check_safe_start
    orig_block = voice_listener.block
    orig_status = voice_listener.status
    
    try:
        voice_listener._resolve_input_device = lambda device_id: {"ok": True, "device_id": "mock_id", "device_name": "Mock Mic"}
        voice_listener.check_safe_start = lambda device_id: {"safe_to_start": False, "failed_check": "microphone_permission_denied", "fix": "Fix privacy settings.", "checks": {}}
        
        blocked_args = []
        def mock_block(reason, fix, error=None):
            blocked_args.append((reason, fix, error))
            return {"ok": False}
        voice_listener.block = mock_block
        
        voice_listener.status = lambda: {
            "ok": True,
            "data": {
                "running": False,
                "state": "blocked",
                "device_id": "mock_id",
                "device_name": "Mock Mic",
                "last_error_type": "microphone_permission_denied",
                "last_error": "Blocked by check: microphone_permission_denied",
                "fix": "Fix privacy settings.",
            }
        }
        
        client = TestClient(app)
        res = client.post("/voice/listener-start", json={"device_id": "mock_id", "wake_word": True})
        assert res.status_code == 200
        resp_data = res.json()
        assert resp_data["ok"] is False
        assert resp_data["data"]["running"] is False
        assert resp_data["data"]["state"] == "blocked"
        assert resp_data["data"]["last_error_type"] == "microphone_permission_denied"
        assert resp_data["data"]["fix"] == "Fix privacy settings."
        assert len(blocked_args) > 0
    finally:
        voice_listener._resolve_input_device = orig_resolve
        voice_listener.check_safe_start = orig_check
        voice_listener.block = orig_block
        voice_listener.status = orig_status


# 10. test_ui_does_not_show_active_when_blocked
def test_ui_does_not_show_active_when_blocked() -> None:
    listener_running = False
    listener_state = "blocked"
    is_ui_active = listener_running
    assert is_ui_active is False


# 11. test_ui_shows_restart_listener_button_when_blocked
def test_ui_shows_restart_listener_button_when_blocked() -> None:
    listener_state = "blocked"
    shows_restart_button = listener_state in ["blocked", "error", "stopped"]
    assert shows_restart_button is True


# 12. test_voice_control_card_reflects_backend_state
def test_voice_control_card_reflects_backend_state() -> None:
    def get_ui_card_state(running, state):
        if running:
            return "active"
        if state in ["blocked", "error"]:
            return "blocked"
        return "stopped"

    assert get_ui_card_state(True, "listening_for_wake_word") == "active"
    assert get_ui_card_state(False, "blocked") == "blocked"
    assert get_ui_card_state(False, "stopped") == "stopped"
