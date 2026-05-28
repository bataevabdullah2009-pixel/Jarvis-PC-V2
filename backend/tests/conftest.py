from __future__ import annotations

import os
import socket
import sys
import winsound
import pytest

# 1. Enforce Test Mode
os.environ["JARVIS_TEST_MODE"] = "true"

# 2. Block external network socket connections
original_connect = socket.socket.connect


def guarded_connect(self, address):
    if isinstance(address, tuple) and len(address) > 0:
        host = address[0]
        # Allow only localhost/127.0.0.1/::1 for TestClient connections
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError(f"REAL_PROVIDER_USED_IN_TESTS: Attempted network connection to {host}")
    return original_connect(self, address)


socket.socket.connect = guarded_connect

# 3. Block sounddevice
try:
    import sounddevice as sd

    def fake_input_stream(*args, **kwargs):
        raise RuntimeError("REAL_PROVIDER_USED_IN_TESTS: sounddevice.InputStream used in tests.")

    sd.InputStream = fake_input_stream
except Exception:
    pass

# 4. Block winsound and pygame mixer
def fake_playsound(*args, **kwargs):
    raise RuntimeError("REAL_PROVIDER_USED_IN_TESTS: winsound.PlaySound used in tests.")


winsound.PlaySound = fake_playsound

try:
    import pygame

    def fake_pygame_init(*args, **kwargs):
        raise RuntimeError("REAL_PROVIDER_USED_IN_TESTS: pygame.mixer used in tests.")

    pygame.mixer.init = fake_pygame_init
    pygame.mixer.music.load = fake_pygame_init
    pygame.mixer.music.play = fake_pygame_init
except Exception:
    pass


# 5. Global Mock/Monkeypatch for AI Planners and TTS Services in conftest
@pytest.fixture(autouse=True)
def mock_all_providers(monkeypatch):
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
    is_ai_unit_test = any(x in current_test for x in ["test_openrouter", "test_groq", "test_api", "test_phase", "test_no_real"])

    if not is_ai_unit_test:
        # Mock GroqPlanner.plan
        from app.providers.groq import GroqPlanner
        from app.providers.openrouter import PlannerResult

        def mock_groq_plan(self, text, context=None):
            return PlannerResult(
                status="answered",
                answer_text="Mock Groq OK",
                actions=[],
                provider="groq",
                model="mock-groq-model",
                status_code=200,
                latency_ms=10,
            )

        monkeypatch.setattr(GroqPlanner, "plan", mock_groq_plan)

        # Mock OpenRouterPlanner.plan
        from app.providers.openrouter import OpenRouterPlanner, PlannerResult

        def mock_or_plan(self, text, context=None):
            return PlannerResult(
                status="answered",
                answer_text="Mock OpenRouter OK",
                actions=[],
                provider="openrouter",
                model="mock-openrouter-model",
                status_code=200,
                latency_ms=10,
            )

        monkeypatch.setattr(OpenRouterPlanner, "plan", mock_or_plan)

    # Mock FishAudioTTS.synthesize
    from app.providers.fish_audio import FishAudioTTS

    def mock_fish_synth(self, text):
        return {"ok": True, "audio": b"mock-wav-bytes", "format": "wav", "status": "completed"}

    monkeypatch.setattr(FishAudioTTS, "synthesize", mock_fish_synth)
    monkeypatch.setattr(FishAudioTTS, "available", lambda self: True)

    # Mock OfflineTTS.speak
    if "test_no_real_tts" not in current_test:
        from app.providers.offline_tts import OfflineTTS

        def mock_offline_speak(self, text, dry_run=False):
            return {"ok": True, "spoken": True, "played": True, "status": "completed"}

        monkeypatch.setattr(OfflineTTS, "speak", mock_offline_speak)
        monkeypatch.setattr(OfflineTTS, "available", lambda self: True)

    # Mock EdgeTTSProvider.synthesize
    from app.providers.edge_tts_provider import EdgeTTSProvider

    def mock_edge_synth(self, text):
        return {"ok": True, "audio": b"mock-mp3-bytes", "format": "mp3", "status": "completed"}

    monkeypatch.setattr(EdgeTTSProvider, "synthesize", mock_edge_synth)
    monkeypatch.setattr(EdgeTTSProvider, "available", lambda self: True)

    # Mock STT model loading to avoid real Vosk init on runner
    from app.voice.stt import STTService

    def mock_stt_transcribe(self, capture):
        current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
        if "test_start_listener" in current_test or "test_phase221" in current_test:
            return {"transcript": ""}
        return {"transcript": "джарвис тестовая команда"}

    monkeypatch.setattr(STTService, "transcribe", mock_stt_transcribe)

    # Mock resolves & test microphones to avoid errors on headless systems
    from app.voice import microphone

    def mock_resolve(settings, device_id="default"):
        return {"ok": True, "device_id": "mock_id", "device_name": "Mock Microphone"}

    monkeypatch.setattr(microphone, "resolve_input_device", mock_resolve)
    monkeypatch.setattr(
        microphone,
        "test_microphone",
        lambda device_id, duration_seconds: {
            "ok": True,
            "heard_signal": True,
            "rms": 0.1,
            "peak": 0.1,
            "opened_device": {"id": "mock_id", "name": "Mock Microphone"},
        },
    )

    # Mock audio capture to return a mock capture object without opening sounddevice
    from app.voice import audio_capture

    class MockCapture:
        device = {"id": "mock_id", "name": "Mock Microphone"}
        sample_rate = 16000
        channels = 1
        rms = 0.1
        peak = 0.1
        attempts = []

    monkeypatch.setattr(audio_capture, "capture_audio", lambda *args, **kwargs: MockCapture())
    
    from app.voice import microphone
    monkeypatch.setattr(microphone, "capture_audio", lambda *args, **kwargs: MockCapture())
    
    from app.voice import listener
    monkeypatch.setattr(listener, "capture_audio", lambda *args, **kwargs: MockCapture())
