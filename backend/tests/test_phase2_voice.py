from __future__ import annotations

import time
import pytest
from unittest import mock
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.voice.speech_orchestrator import SpeechOrchestrator
from app.providers.offline_tts import OfflineTTS
from app.voice.speech_queue import speech_queue
from app.main import app

client = TestClient(app)


def test_voice_locked_blocks_fallbacks() -> None:
    """Asserts that when tts_require_fish_audio=True and Fish fails,

    fallbacks to resembling/edge/offline are skipped, returning text_only.
    """
    settings = Settings()
    settings.tts_primary = "fish_audio"
    settings.tts_require_fish_audio = True

    orchestrator = SpeechOrchestrator(settings)

    # Mock all synthesize methods to return failed status or verify offline is not called
    with mock.patch.object(orchestrator.fish, "available", return_value=True), \
         mock.patch.object(orchestrator.fish, "synthesize", return_value={"ok": False, "error": "Quota exceeded", "status": "failed"}), \
         mock.patch.object(orchestrator.offline, "speak") as mock_offline_speak:

        result = orchestrator.say("Привет, сэр.")
        
        assert result["provider"] == "text_only"
        assert result["fallback_used"] is False
        mock_offline_speak.assert_not_called()


def test_voice_fallback_allowed() -> None:
    """Asserts that when tts_require_fish_audio=False and Fish fails,

    the system uses the next available fallback (e.g. pyttsx3).
    """
    settings = Settings()
    settings.tts_primary = "fish_audio"
    settings.tts_require_fish_audio = False
    settings.tts_fallback_enabled = True

    orchestrator = SpeechOrchestrator(settings)

    with mock.patch.object(orchestrator.fish, "available", return_value=True), \
         mock.patch.object(orchestrator.fish, "synthesize", return_value={"ok": False, "error": "Network fail", "status": "failed"}), \
         mock.patch.object(orchestrator.resemble, "available", return_value=False), \
         mock.patch.object(orchestrator.edge, "available", return_value=False), \
         mock.patch.object(orchestrator.offline, "available", return_value=True), \
         mock.patch.object(orchestrator.offline, "speak", return_value={"ok": True, "provider": "pyttsx3", "status": "completed"}) as mock_offline_speak:

        result = orchestrator.say("Привет, сэр.")
        
        assert result["provider"] == "pyttsx3"
        assert result["fallback_used"] is True
        mock_offline_speak.assert_called_once()


def test_assistant_ask_does_not_wait_for_tts() -> None:
    """Asserts that when wait_for_tts=False (default for user),

    ask endpoint returns the text response immediately without blocking on TTS.
    """
    from app.providers.openrouter import PlannerResult
    
    # Mock TTSService speak to sleep for 3 seconds
    def slow_speak(text, dry_run=False, blocking=False):
        time.sleep(3.0)
        return {"ok": True, "provider": "fish_audio", "status": "completed"}

    # Mock AI plan to return instantly
    with mock.patch("app.router.ai_planner.AIPlanner.plan") as mock_plan, \
         mock.patch("app.voice.tts.TTSService.speak", side_effect=slow_speak):
         
        mock_plan.return_value = PlannerResult(
            status="answered",
            answer_text="Привет, сэр.",
            actions=[],
            provider="openrouter",
            latency_ms=10,
            openrouter_called=True
        )
        started = time.perf_counter()
        
        response = client.post(
            "/assistant/ask",
            json={
                "text": "Как дела?",
                "speak": True,
                "source": "hud",
                "context": {"wait_for_tts": False}
            }
        )
        
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        
        assert response.status_code == 200
        # Should return very quickly since TTS is asynchronous in SpeechQueue
        assert elapsed_ms < 800
        body = response.json()
        assert body["ok"] is True
        assert body["data"]["tts"]["status"] == "queued"


def test_assistant_ask_wait_for_tts_debug() -> None:
    """Asserts that when wait_for_tts=True (debug/test mode),

    ask endpoint waits for TTS before returning.
    """
    from app.providers.openrouter import PlannerResult

    def fast_speak(text, dry_run=False, blocking=False):
        time.sleep(0.5)
        return {"ok": True, "provider": "fish_audio", "status": "completed"}

    with mock.patch("app.router.ai_planner.AIPlanner.plan") as mock_plan, \
         mock.patch("app.voice.tts.TTSService.speak", side_effect=fast_speak):
         
        mock_plan.return_value = PlannerResult(
            status="answered",
            answer_text="Привет, сэр.",
            actions=[],
            provider="openrouter",
            latency_ms=10,
            openrouter_called=True
        )
        started = time.perf_counter()
        
        response = client.post(
            "/assistant/ask",
            json={
                "text": "Тест задержки.",
                "speak": True,
                "source": "hud",
                "context": {"wait_for_tts": True}
            }
        )
        
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        
        assert response.status_code == 200
        # Must block and take at least 500ms
        assert elapsed_ms >= 500


def test_single_tts_queue() -> None:
    """Asserts that when multiple TTS jobs are submitted rapidly,

    only the last job actively plays, and previous jobs are cancelled.
    """
    from app.events.websocket_bus import event_bus
    event_bus.events.clear()
    
    # Mock speak to take some time so we can submit rapidly
    def slow_speak(text, dry_run=False, blocking=False):
        for _ in range(5):
            if speech_queue._cancel_event.is_set():
                break
            time.sleep(0.1)
        return {"ok": True, "provider": "fish_audio", "status": "completed"}
        
    tts_mock = mock.MagicMock()
    tts_mock.speak.side_effect = slow_speak
    
    # Submit 3 items in a row
    speech_queue.submit("cmd_1", "route_1", "Первый", tts_mock)
    speech_queue.submit("cmd_2", "route_2", "Второй", tts_mock)
    speech_queue.submit("cmd_3", "route_3", "Третий", tts_mock)
    
    # Sleep to let worker complete
    time.sleep(1.0)
    
    tasks_cancelled = [
        e["payload"]["command_id"] for e in event_bus.events 
        if e["type"] == "assistant.tts.cancelled"
    ]
    
    # cmd_1 and cmd_2 must have been cancelled
    assert "cmd_1" in tasks_cancelled
    assert "cmd_2" in tasks_cancelled


def test_openrouter_fast_defaults() -> None:
    """Asserts that Settings loads fast default timeouts and tokens for OpenRouter."""
    settings = Settings.load()
    
    assert settings.openrouter_max_tokens <= 200
    assert settings.openrouter_max_retries == 0
    assert settings.openrouter_total_timeout <= 10
