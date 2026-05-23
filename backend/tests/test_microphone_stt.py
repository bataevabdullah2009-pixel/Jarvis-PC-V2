from __future__ import annotations

from unittest import mock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.voice.microphone import AudioCapture, VoiceDependencyError
from app.voice.voice_pipeline import VoicePipeline
from app.main import app

client = TestClient(app)


def test_microphone_dependency_check_shape() -> None:
    """Verifies that GET /voice/mic-diagnostics returns the correct JSON structure."""
    response = client.get("/voice/mic-diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert "sounddevice_available" in data
    assert "numpy_available" in data
    assert "default_input_device" in data
    assert "input_devices" in data
    assert "windows_hint" in data
    assert "can_record" in data
    assert "fixes" in data


def test_stt_status_no_model() -> None:
    """Verifies that if Vosk model is missing, configured=False, there is a fix, and model_path is present."""
    settings = Settings()
    settings.vosk_model_path = "models/non_existent_model_xyz"

    with mock.patch("importlib.util.find_spec", return_value=True):
        from app.voice.stt import stt_status
        status = stt_status(settings)
        assert status["configured"] is False
        assert status["model_exists"] is False
        assert "non_existent_model_xyz" in status["model_path"]
        assert len(status["fixes"]) > 0
        assert "Скачайте модель Vosk" in status["fixes"][0]


def test_record_command_no_audio(monkeypatch) -> None:
    """Asserts that if capture returns rms=0 and peak=0, final_status='no_audio'."""
    def fake_capture_audio(**kwargs):
        return AudioCapture(
            sample_rate=16000,
            channels=1,
            samples=[0.0],
            rms=0.0,
            peak=0.0
        )

    monkeypatch.setattr("app.voice.voice_pipeline.capture_audio", fake_capture_audio)

    settings = Settings()
    pipeline = VoicePipeline(settings)
    result = pipeline.record_command(device_id="default", max_seconds=1, send_to_assistant=False)

    assert result["ok"] is False
    assert result["final_status"] == "no_audio"
    assert result["capture"]["heard_signal"] is False


def test_record_command_stt_not_configured(monkeypatch) -> None:
    """Asserts that if capture has signal but STT is not configured, final_status='stt_not_configured'."""
    def fake_capture_audio(**kwargs):
        return AudioCapture(
            sample_rate=16000,
            channels=1,
            samples=[0.5],
            rms=0.1,
            peak=0.5
        )

    monkeypatch.setattr("app.voice.voice_pipeline.capture_audio", fake_capture_audio)

    def fake_stt_dependency_status(*args, **kwargs):
        return {"configured": False}

    monkeypatch.setattr("app.voice.voice_pipeline.stt_dependency_status", fake_stt_dependency_status)

    settings = Settings()
    pipeline = VoicePipeline(settings)
    result = pipeline.record_command(device_id="default", max_seconds=1, send_to_assistant=False)

    assert result["ok"] is False
    assert result["final_status"] == "stt_not_configured"
    assert result["stt"]["configured"] is False


def test_record_command_transcript_to_assistant(monkeypatch) -> None:
    """Asserts that if transcript is found, CommandRouter is invoked and final_status='sent_to_assistant'."""
    def fake_capture_audio(**kwargs):
        return AudioCapture(
            sample_rate=16000,
            channels=1,
            samples=[0.5],
            rms=0.1,
            peak=0.5
        )

    monkeypatch.setattr("app.voice.voice_pipeline.capture_audio", fake_capture_audio)

    def fake_stt_dependency_status(*args, **kwargs):
        return {"configured": True}

    monkeypatch.setattr("app.voice.voice_pipeline.stt_dependency_status", fake_stt_dependency_status)

    def fake_transcribe(*args, **kwargs):
        return {
            "configured": True,
            "provider": "vosk",
            "transcript": "джарвис как дела",
            "error": None
        }

    monkeypatch.setattr("app.voice.stt.STTService.transcribe", fake_transcribe)

    mock_router_handle = mock.MagicMock(return_value={"ok": True, "route": "chat", "response_text": "Привет!"})
    monkeypatch.setattr("app.router.command_router.CommandRouter.handle", mock_router_handle)

    settings = Settings()
    pipeline = VoicePipeline(settings)
    result = pipeline.record_command(device_id="default", max_seconds=1, send_to_assistant=True)

    assert result["ok"] is True
    assert result["final_status"] == "sent_to_assistant"
    assert result["stt"]["transcript"] == "джарвис как дела"
    mock_router_handle.assert_called_once_with("джарвис как дела", source="voice", context={"dry_run": False, "speak": True, "wait_for_tts": False})


def test_ui_device_id_sent() -> None:
    """Verifies that the /voice/record-command and /voice/test-capture endpoints receive and respect device_id from frontend requests."""
    with mock.patch("app.voice.voice_pipeline.VoicePipeline.record_command") as mock_record:
        mock_record.return_value = {"ok": True, "final_status": "recorded"}
        response = client.post(
            "/voice/record-command",
            json={"device_id": "99", "max_seconds": 4, "send_to_assistant": False}
        )
        assert response.status_code == 200
        mock_record.assert_called_once_with(
            device_id="99",
            max_seconds=4.0,
            send_to_assistant=False,
            text_override=None,
            dry_run=False
        )

    with mock.patch("app.voice.microphone.capture_audio") as mock_capture:
        mock_capture.return_value = mock.Mock(sample_rate=16000, channels=1, rms=0.1, peak=0.5)
        response = client.post(
            "/voice/test-capture",
            json={"device_id": "12", "duration_seconds": 2}
        )
        assert response.status_code == 200
        mock_capture.assert_called_once_with(
            device_id="12",
            duration_seconds=2.0
        )
