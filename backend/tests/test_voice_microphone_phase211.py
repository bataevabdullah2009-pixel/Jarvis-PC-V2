from __future__ import annotations

from unittest import mock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.voice.microphone import AudioCapture, VoiceDependencyError
from app.voice.voice_pipeline import VoicePipeline
from app.main import app

client = TestClient(app)


def test_record_command_no_500_on_default(monkeypatch) -> None:
    """Verifies that record-command does not crash 500 when given 'default' but returns structured JSON."""
    # Mock capture_audio to throw an exception to test that it is handled gracefully and returns structured JSON
    def fake_capture_audio(**kwargs):
        raise ValueError("Simulated hardware failure")

    monkeypatch.setattr("app.voice.voice_pipeline.capture_audio", fake_capture_audio)

    # Mock resolve_input_device to return success
    def fake_resolve_input_device(device_id):
        return {
            "ok": True,
            "device_id": 0,
            "device_name": "Mock Default Mic",
            "sample_rate": 16000,
            "channels": 1,
            "error_type": None,
            "fix": None,
        }
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", fake_resolve_input_device)

    response = client.post(
        "/voice/record-command",
        json={"device_id": "default", "max_seconds": 1, "send_to_assistant": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["data"]["final_status"] == "record_error"
    assert "error" in body
    assert body["error"]["code"] == "VOICE_RECORD_ERROR"


def test_record_command_device_id_string(monkeypatch) -> None:
    """Verifies that device_id="1" resolves correctly without crash."""
    resolved_devices = []

    def fake_resolve_input_device(device_id):
        resolved_devices.append(device_id)
        return {
            "ok": True,
            "device_id": 1,
            "device_name": "Mock Mic 1",
            "sample_rate": 16000,
            "channels": 1,
            "error_type": None,
            "fix": None,
        }
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", fake_resolve_input_device)

    def fake_capture_audio(**kwargs):
        return AudioCapture(
            sample_rate=16000,
            channels=1,
            samples=[0.0],
            rms=0.0,
            peak=0.0
        )
    monkeypatch.setattr("app.voice.voice_pipeline.capture_audio", fake_capture_audio)

    response = client.post(
        "/voice/record-command",
        json={"device_id": "1", "max_seconds": 1, "send_to_assistant": False}
    )
    assert response.status_code == 200
    assert "1" in resolved_devices


def test_record_command_no_audio(monkeypatch) -> None:
    """Asserts that if capture returns rms=0 and peak=0, final_status='no_audio'."""
    def fake_resolve_input_device(device_id):
        return {
            "ok": True,
            "device_id": 1,
            "device_name": "Mock Mic",
            "sample_rate": 16000,
            "channels": 1,
            "error_type": None,
            "fix": None,
        }
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", fake_resolve_input_device)

    def fake_capture_audio(**kwargs):
        return AudioCapture(
            sample_rate=16000,
            channels=1,
            samples=[0.0],
            rms=0.0,
            peak=0.0
        )
    monkeypatch.setattr("app.voice.voice_pipeline.capture_audio", fake_capture_audio)

    response = client.post(
        "/voice/record-command",
        json={"device_id": "default", "max_seconds": 1, "send_to_assistant": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["data"]["final_status"] == "no_audio"
    assert body["data"]["capture"]["heard_signal"] is False


def test_record_command_stt_not_configured(monkeypatch) -> None:
    """Asserts that if capture has signal but STT is not configured, final_status='stt_not_configured'."""
    def fake_resolve_input_device(device_id):
        return {
            "ok": True,
            "device_id": 1,
            "device_name": "Mock Mic",
            "sample_rate": 16000,
            "channels": 1,
            "error_type": None,
            "fix": None,
        }
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", fake_resolve_input_device)

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

    response = client.post(
        "/voice/record-command",
        json={"device_id": "default", "max_seconds": 1, "send_to_assistant": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["data"]["final_status"] == "stt_not_configured"
    assert body["data"]["stt"]["configured"] is False


def test_record_command_transcript_to_assistant(monkeypatch) -> None:
    """Asserts that if transcript is found, AssistantOrchestrator.ask is invoked and final_status='sent_to_assistant'."""
    def fake_resolve_input_device(device_id):
        return {
            "ok": True,
            "device_id": 1,
            "device_name": "Mock Mic",
            "sample_rate": 16000,
            "channels": 1,
            "error_type": None,
            "fix": None,
        }
    monkeypatch.setattr("app.voice.microphone.resolve_input_device", fake_resolve_input_device)

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
            "transcript": "привет джарвис",
            "error": None
        }
    monkeypatch.setattr("app.voice.stt.STTService.transcribe", fake_transcribe)

    # Mock the AssistantOrchestrator.ask async method
    async def fake_ask(*args, **kwargs):
        return {"ok": True, "route": "chat", "response_text": "Привет!"}
    monkeypatch.setattr("app.core.assistant_orchestrator.AssistantOrchestrator.ask", fake_ask)

    response = client.post(
        "/voice/record-command",
        json={"device_id": "default", "max_seconds": 1, "send_to_assistant": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["final_status"] == "sent_to_assistant"
    assert body["data"]["stt"]["transcript"] == "привет джарвис"
    assert body["data"]["assistant_result"]["response_text"] == "Привет!"


def test_mic_diagnostics_shape() -> None:
    """Verifies that /voice/mic-diagnostics returns the correct data and list of input_devices."""
    response = client.get("/voice/mic-diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert "sounddevice_available" in data
    assert "numpy_available" in data
    assert "default_input_device" in data
    assert "input_devices" in data
    assert "selected_device_id" in data
    assert "can_record" in data
    assert "windows_microphone_hint" in data
    assert "fixes" in data


def test_stt_status_shape() -> None:
    """Verifies that /voice/stt-status returns the configured status, model path, and fixes list."""
    response = client.get("/voice/stt-status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert "provider" in data
    assert "vosk_available" in data
    assert "model_path" in data
    assert "model_exists" in data
    assert "configured" in data
    assert "language" in data
    assert "fixes" in data
