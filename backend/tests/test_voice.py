from app.main import app
from app.voice.microphone import AudioCapture, dependency_check, test_microphone as run_microphone_test
from app.voice.wake import listener_state
from fastapi.testclient import TestClient


client = TestClient(app)


def test_voice_dependency_check_shape() -> None:
    data = dependency_check()
    assert "sounddevice" in data
    assert "numpy" in data
    assert "microphone" in data


def test_microphone_metrics_can_be_computed_with_fake_capture(monkeypatch) -> None:
    def fake_capture_audio(**kwargs):
        return AudioCapture(
            sample_rate=16000,
            channels=1,
            samples=[0.1],
            rms=0.1,
            peak=0.2,
        )

    monkeypatch.setattr("app.voice.microphone.capture_audio", fake_capture_audio)
    result = run_microphone_test(device_id="default", duration_seconds=1)
    assert result["rms"] == 0.1
    assert result["peak"] == 0.2
    assert result["heard_signal"] is True


def test_api_voice_dependency_check() -> None:
    response = client.get("/voice/dependency-check")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["data"]["stt"]["configured"], bool)
    if body["data"]["stt"]["configured"]:
        assert body["data"]["stt"]["provider"] == "vosk"
    assert body["data"]["tts"]["mode"] == "fish_audio_primary"
    assert "fish_audio" in body["data"]["tts"]["providers"]


def test_record_command_with_text_override_routes_to_assistant() -> None:
    response = client.post(
        "/voice/record-command",
        json={
            "device_id": "default",
            "max_seconds": 1,
            "send_to_assistant": True,
            "text_override": "Джарвис, я вернулся",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["transcript"] == "Джарвис, я вернулся"
    assert body["data"]["assistant_result"]["route"] == "scenario"
    assert body["data"]["assistant_result"]["route_detail"] == "scenario:welcome_home"


def test_listener_start_stop(monkeypatch) -> None:
    # Mock safe gate checks to pass
    monkeypatch.setattr("app.voice.listener.resolve_input_device", lambda dev_id: {
        "ok": True, "device_name": "Test Mic", "sample_rate": 16000, "channels": 1
    })
    monkeypatch.setattr("app.voice.listener.test_microphone", lambda device_id, duration_seconds: {
        "heard_signal": True, "rms": 0.1, "peak": 0.1
    })
    monkeypatch.setattr("app.voice.listener.stt_dependency_status", lambda settings: {
        "configured": True, "provider": "vosk"
    })
    monkeypatch.setattr("app.voice.listener.is_speaking_now", lambda: False)
    
    start = client.post(
        "/voice/start-listener",
        json={"wake_word": True, "clap": False, "device_id": "default"},
    )
    assert start.status_code == 200
    assert start.json()["data"]["running"] is True
    assert listener_state.running is True

    stop = client.post("/voice/stop-listener")
    assert stop.status_code == 200
    assert stop.json()["data"]["running"] is False
    assert listener_state.running is False
