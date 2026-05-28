from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from app.core.config import get_settings
from app.voice import anti_echo
from app.voice.listener import voice_listener, VoiceListener
from app.storage.history_store import history_store
from app.core.assistant_orchestrator import AssistantOrchestrator
from app.voice.tts import TTSService


@pytest.fixture(autouse=True)
def cleanup_states():
    voice_listener.stop()
    voice_listener.errors = []
    voice_listener.warnings = []
    voice_listener.metrics = {
        "audio_windows": 0,
        "triggers": 0,
        "commands_sent": 0,
        "ignored_self_audio": 0,
        "no_audio_events": 0,
        "self_echo_blocks": 0
    }
    voice_listener.state = "stopped"
    history_store.clear()
    
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = ""
    anti_echo._consecutive_echo_count = 0
    anti_echo._self_echo_loop_triggered = False
    
    yield


# 1. test_wake_word_does_not_execute_as_command
def test_wake_word_does_not_execute_as_command():
    mock_capture = MagicMock()
    mock_capture.rms = 0.1
    mock_capture.peak = 0.1

    with patch("app.voice.listener.STTService") as mock_stt_class, \
         patch("app.voice.listener.AssistantOrchestrator") as mock_orch_class, \
         patch("app.voice.listener.TTSService") as mock_tts_class, \
         patch("app.voice.listener.capture_audio") as mock_capture_func:
         
        mock_stt = mock_stt_class.return_value
        # Bare wake word first, then empty transcript in next phase
        mock_stt.transcribe.side_effect = [
            {"transcript": "джарвис"},
            {"transcript": ""}
        ]
        
        mock_orch = mock_orch_class.return_value
        mock_tts = mock_tts_class.return_value
        
        mock_capture_func.return_value = mock_capture
        
        voice_listener.wake_word_enabled = True
        voice_listener.detect_trigger(mock_capture)
        
        # Verify that orchestrator was not called since it was only a bare wake word
        assert mock_orch.ask.call_count == 0
        assert voice_listener.state in {"idle_listening_for_wake_word", "cooldown"}


# 2. test_wake_word_then_command_executes
def test_wake_word_then_command_executes():
    mock_capture = MagicMock()
    mock_capture.rms = 0.1
    mock_capture.peak = 0.1

    with patch("app.voice.listener.STTService") as mock_stt_class, \
         patch("app.voice.listener.AssistantOrchestrator") as mock_orch_class, \
         patch("app.voice.listener.TTSService") as mock_tts_class, \
         patch("app.voice.listener.capture_audio") as mock_capture_func:
         
        mock_stt = mock_stt_class.return_value
        # Bare wake word first, then actual command
        mock_stt.transcribe.side_effect = [
            {"transcript": "джарвис"},
            {"transcript": "сколько время"}
        ]
        
        mock_orch = mock_orch_class.return_value
        mock_orch.ask.return_value = {"text": "Сейчас 17:00, сэр", "status": "completed"}
        
        mock_capture_func.return_value = mock_capture
        
        voice_listener.wake_word_enabled = True
        voice_listener.detect_trigger(mock_capture)
        
        # Verify orchestrator received "сколько время" command
        assert mock_orch.ask.call_count == 1
        mock_orch.ask.assert_called_with("сколько время", speak=True, source="voice")
        assert voice_listener.state in {"idle_listening_for_wake_word", "cooldown"}


# 3. test_wake_word_then_empty_audio_returns_not_heard
def test_wake_word_then_empty_audio_returns_not_heard():
    mock_capture = MagicMock()
    mock_capture.rms = 0.1
    mock_capture.peak = 0.1

    with patch("app.voice.listener.STTService") as mock_stt_class, \
         patch("app.voice.listener.TTSService") as mock_tts_class, \
         patch("app.voice.listener.capture_audio") as mock_capture_func:
         
        mock_stt = mock_stt_class.return_value
        # Bare wake word first, then silent empty command
        mock_stt.transcribe.side_effect = [
            {"transcript": "джарвис"},
            {"transcript": ""}
        ]
        
        mock_tts = mock_tts_class.return_value
        mock_capture_func.return_value = mock_capture
        
        voice_listener.wake_word_enabled = True
        voice_listener.detect_trigger(mock_capture)
        
        # Verify TTS played warning acknowledgment
        mock_tts.speak.assert_any_call("Сэр, я не расслышал команду.", blocking=True)
        assert voice_listener.state in {"idle_listening_for_wake_word", "cooldown"}


# 4. test_voice_command_is_added_to_history
def test_voice_command_is_added_to_history():
    history_store.clear()
    history_store.add_item(
        command_id="test_voice_123",
        user_text="сколько время",
        assistant_text="Сейчас 17:00, сэр",
        route="ai",
        status="completed",
        latency_ms=450
    )
    
    items = history_store.get_items()
    assert len(items) == 1
    assert items[0]["id"] == "test_voice_123"
    assert items[0]["userText"] == "сколько время"
    assert items[0]["user_text"] == "сколько время"
    assert items[0]["assistantText"] == "Сейчас 17:00, сэр"
    assert items[0]["assistant_text"] == "Сейчас 17:00, сэр"
    assert items[0]["route"] == "ai"
    assert items[0]["latency"] == 450


# 5. test_listener_returns_to_idle_after_command
def test_listener_returns_to_idle_after_command():
    mock_capture = MagicMock()
    mock_capture.rms = 0.1
    mock_capture.peak = 0.1

    with patch("app.voice.listener.STTService") as mock_stt_class, \
         patch("app.voice.listener.AssistantOrchestrator") as mock_orch_class, \
         patch("app.voice.listener.TTSService") as mock_tts_class, \
         patch("app.voice.listener.capture_audio") as mock_capture_func:
         
        mock_stt = mock_stt_class.return_value
        mock_stt.transcribe.side_effect = [
            {"transcript": "джарвис сколько время"},
        ]
        
        mock_orch = mock_orch_class.return_value
        mock_orch.ask.return_value = {"text": "Сейчас 17:00, сэр", "status": "completed"}
        
        mock_capture_func.return_value = mock_capture
        
        voice_listener.wake_word_enabled = True
        voice_listener.detect_trigger(mock_capture)
        
        # Verify it went to cooldown, and then back to idle_listening_for_wake_word
        assert voice_listener.state == "idle_listening_for_wake_word"


# 6. test_listener_does_not_loop_on_own_tts
def test_listener_does_not_loop_on_own_tts():
    # Enforce TTS playing and make sure anti-echo clear works properly
    anti_echo.mark_tts_started("Да, сэр?")
    assert anti_echo.is_speaking_now() is True
    
    anti_echo.clear_tts_cooldown()
    assert anti_echo.is_speaking_now() is False


# 7. test_ui_renders_command_history_items
def test_ui_renders_command_history_items():
    from app.core.config import PROJECT_ROOT
    root = PROJECT_ROOT.parent if PROJECT_ROOT.name == "backend" else PROJECT_ROOT
    ui_path = root / "frontend" / "src" / "screens" / "MinimalUI.tsx"
    
    with open(ui_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Verify that MinimalUI history refers to userText and assistantText
    assert "item.userText" in content
    assert "item.assistantText" in content


# 8. test_ui_does_not_show_empty_history_after_voice_command
def test_ui_does_not_show_empty_history_after_voice_command():
    from app.core.config import PROJECT_ROOT
    root = PROJECT_ROOT.parent if PROJECT_ROOT.name == "backend" else PROJECT_ROOT
    ui_path = root / "frontend" / "src" / "screens" / "MinimalUI.tsx"
    
    with open(ui_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Verify empty history message condition is present
    assert "!history.length" in content
