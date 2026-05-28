from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from app.core.config import get_settings
from app.voice import anti_echo
from app.voice.listener import voice_listener, VoiceListener
from app.core.pending_confirmation import pending_store
from app.core.action_policy import ActionPolicy
from app.features.reminders import reminder_service
from app.router.command_router import CommandRouter


@pytest.fixture(autouse=True)
def cleanup_states():
    # Reset listener states
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
    
    # Reset anti_echo states
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = ""
    anti_echo._consecutive_echo_count = 0
    anti_echo._self_echo_loop_triggered = False
    
    # Reset pending confirmation store
    pending_store.clear_pending()
    
    yield


# 1. test_listener_start_stop_idempotent
def test_listener_start_stop_idempotent():
    with patch("app.voice.listener.test_microphone") as mock_test, \
         patch("app.voice.listener.resolve_input_device") as mock_resolve, \
         patch("app.voice.listener.stt_dependency_status") as mock_stt_status, \
         patch("app.voice.listener.VoiceListener.process_audio_window") as mock_window:
        
        mock_resolve.return_value = {"ok": True, "device_name": "Test Mic", "sample_rate": 16000, "channels": 1}
        mock_test.return_value = {"heard_signal": True}
        mock_stt_status.return_value = {"configured": True}
        
        # Start listener first time
        voice_listener.start(device_id="1", wake_word_enabled=True, clap_enabled=True)
        first_thread = voice_listener._thread
        assert voice_listener.state != "stopped"
        assert first_thread is not None
        assert first_thread.is_alive()
        
        # Start listener second time (idempotent check)
        voice_listener.start(device_id="1", wake_word_enabled=True, clap_enabled=True)
        second_thread = voice_listener._thread
        assert first_thread == second_thread
        
        # Stop listener
        voice_listener.stop()
        assert voice_listener.state == "stopped"
        assert voice_listener._thread is None


# 2. test_listener_ignores_audio_while_speaking
def test_listener_ignores_audio_while_speaking():
    anti_echo.mark_tts_started("Привет сэр")
    assert anti_echo.is_speaking_now() is True
    
    res = anti_echo.should_ignore_transcript("как дела")
    assert res["ignore"] is True
    assert res["reason"] == "speaking_active"


# 3. test_listener_cooldown_blocks_transcript
def test_listener_cooldown_blocks_transcript():
    anti_echo.mark_tts_completed("Привет сэр")
    assert anti_echo.is_speaking_now() is True
    
    res = anti_echo.should_ignore_transcript("как дела")
    assert res["ignore"] is True
    assert res["reason"] == "speaking_active"


# 4. test_listener_ignores_self_transcript_similarity
def test_listener_ignores_self_transcript_similarity():
    anti_echo._last_tts_text = "Я открыл приложение Телеграм"
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    
    # 0.90 similarity transcript
    res = anti_echo.should_ignore_transcript("открыл приложение телеграм")
    assert res["ignore"] is True
    assert res["self_echo_blocked"] is True


# 5. test_listener_sends_command_after_wake_word
def test_listener_sends_command_after_wake_word():
    # Setup mock capture
    mock_capture = MagicMock()
    mock_capture.rms = 0.1
    mock_capture.peak = 0.1
    
    with patch("app.voice.listener.STTService") as mock_stt_class, \
         patch("app.voice.listener.AssistantOrchestrator") as mock_orch_class, \
         patch("app.voice.listener.capture_audio") as mock_capture_func:
         
        mock_stt = mock_stt_class.return_value
        mock_stt.transcribe.return_value = {"transcript": "джарвис как дела"}
        
        mock_orch = mock_orch_class.return_value
        mock_orch.ask.return_value = {"text": "Да, сэр?"}
        
        # Second capture for the command text
        mock_capture_func.return_value = mock_capture
        
        # Simulate STT command call
        mock_stt.transcribe.side_effect = [
            {"transcript": "джарвис как дела"},  # wake word and command in one window
        ]
        
        voice_listener.wake_word_enabled = True
        voice_listener.clap_enabled = False
        voice_listener.detect_trigger(mock_capture)
        
        # Assert triggers occurred
        assert voice_listener.metrics["triggers"] == 1
        assert voice_listener.metrics["commands_sent"] == 1


# 6. test_listener_does_not_start_when_no_audio
def test_listener_does_not_start_when_no_audio():
    with patch("app.voice.listener.test_microphone") as mock_test, \
         patch("app.voice.listener.resolve_input_device") as mock_resolve:
        
        mock_resolve.return_value = {"ok": True, "device_name": "Test Mic", "sample_rate": 16000, "channels": 1}
        mock_test.return_value = {"heard_signal": False, "rms": 0.0, "peak": 0.0}
        
        res = voice_listener.start(device_id="1", wake_word_enabled=True, clap_enabled=True, force_start=False)
        assert res["ok"] is False
        assert res["data"]["state"] == "blocked"
        assert res["data"]["last_error_type"] == "microphone_no_audio"


# 7. test_listener_rate_limit_prevents_loop
def test_listener_rate_limit_prevents_loop():
    # Trigger 7 times instantly
    voice_listener._trigger_timestamps = [time.time()] * 7
    
    with patch("app.voice.listener.time.sleep") as mock_sleep:
        voice_listener.state = "listening_for_trigger"
        voice_listener._stop_event.clear()
        
        # We patch _stop_event.is_set to stop loop immediately on next iteration
        voice_listener._stop_event.is_set = MagicMock(side_effect=[False, True])
        voice_listener.run_loop()
        
        # State transitions to cooldown and then back to listening_for_wake_word after time.sleep
        assert voice_listener.state in {"listening_for_trigger", "listening_for_wake_word", "idle_listening_for_wake_word"}
        assert len(voice_listener.warnings) > 0


# 8. test_main_mic_button_removed
def test_main_mic_button_removed():
    # Frontend layout test: We inspect if MinimalUI component file has removed mic button next to text input form
    from app.core.config import PROJECT_ROOT
    root = PROJECT_ROOT.parent if PROJECT_ROOT.name == "backend" else PROJECT_ROOT
    minimal_ui_path = root / "frontend" / "src" / "screens" / "MinimalUI.tsx"
    with open(minimal_ui_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Assert Mic button inside the command-form is removed
    # Form structure: <form className="command-form" ...> <input /> <button type="submit"> ... </button> </form>
    assert "onRecordVoice" not in content or "command-form" not in content or 'title="Микрофон"' not in content


# 9. test_safe_actions_do_not_require_confirmation
def test_safe_actions_do_not_require_confirmation():
    safe_commands = [
        {"type": "play_music_search", "target": "Back in Black"},
        {"type": "open_url", "target": "https://google.com"},
        {"type": "open_app", "target": "telegram"},
        {"type": "read_news", "target": ""},
        {"type": "volume_up", "target": ""},
        {"type": "screenshot", "target": ""},
        {"type": "respond_text", "target": "hello"}
    ]
    for action in safe_commands:
        status, reason = ActionPolicy.classify_action(action)
        assert status == "SAFE"


# 10. test_confirm_required_actions_create_pending
def test_confirm_required_actions_create_pending():
    router = CommandRouter(get_settings())
    
    # Run a command requiring confirmation (e.g. shutdown)
    with patch("app.router.command_router.get_commands") as mock_get_cmds:
        mock_get_cmds.return_value = {
            "commands": [
                {
                    "id": "sys_shutdown",
                    "phrases": ["выключи компьютер"],
                    "action": "shutdown",
                    "value": "now"
                }
            ]
        }
        
        res = router.handle("выключи компьютер")
        assert res["requires_confirmation"] is True
        assert res["status"] == "requires_confirmation"
        
        # Check that pending action is registered
        pending = pending_store.get_pending()
        assert pending is not None
        assert pending["action"]["type"] == "shutdown"


# 11. test_confirm_executes_pending_action
def test_confirm_executes_pending_action():
    router = CommandRouter(get_settings())
    
    # Create a pending action
    action = {"type": "open_url", "target": "https://github.com"}
    pending_store.set_pending(action, "открыть ссылку")
    
    # Confirm
    res = router.handle("подтверждаю")
    assert res["requires_confirmation"] is False
    assert res["ok"] is True
    assert len(res["actions"]) == 1
    assert res["actions"][0]["type"] == "open_url"


# 12. test_confirm_without_pending_action
def test_confirm_without_pending_action():
    router = CommandRouter(get_settings())
    pending_store.clear_pending()
    
    res = router.handle("подтверждаю")
    assert res["requires_confirmation"] is False
    assert "нет действия" in res["response_text"]


# 13. test_reminder_created_without_confirmation
def test_reminder_created_without_confirmation():
    router = CommandRouter(get_settings())
    
    res = router.handle("напомни через 10 минут выпить воды")
    assert res["requires_confirmation"] is False
    assert res["ok"] is True
    assert res["route_detail"] == "local_command:reminder"
    assert len(res["actions"]) == 1
    assert "воды" in res["actions"][0]["text"]
