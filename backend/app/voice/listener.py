from __future__ import annotations

import time
import logging
import asyncio
import threading
from typing import Any, Dict, List
from datetime import datetime
from app.core.config import get_settings
from app.events.websocket_bus import event_bus
from app.voice.microphone import capture_audio, resolve_input_device, test_microphone, VoiceDependencyError
from app.voice.stt import STTService, stt_dependency_status
from app.voice.anti_echo import (
    should_ignore_transcript,
    is_speaking_now,
    check_loopback_device
)
from app.core.assistant_orchestrator import AssistantOrchestrator

logger = logging.getLogger("jarvis.listener")


class VoiceListener:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VoiceListener, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        
        self.state = "stopped"  # stopped, idle, listening_for_trigger, triggered, recording_command, transcribing, sending_to_assistant, speaking, cooldown, error
        self.device_id = "default"
        self.device_name = "Default Device"
        self.wake_word_enabled = True
        self.clap_enabled = True
        
        self.last_trigger = ""
        self.last_transcript = ""
        self.last_ignored_reason = ""
        self.cooldown_until = 0.0
        
        self.errors: list[str] = []
        self.warnings: list[str] = []
        
        # Metrics
        self.metrics = {
            "audio_windows": 0,
            "triggers": 0,
            "commands_sent": 0,
            "ignored_self_audio": 0,
            "no_audio_events": 0,
            "self_echo_blocks": 0
        }
        
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._trigger_timestamps: list[float] = []
        
        self._initialized = True

    def start(self, device_id: str = "default", wake_word_enabled: bool = True, clap_enabled: bool = True, force_start: bool = False) -> dict[str, Any]:
        """Starts the background listening thread if not already running."""
        with self._lock:
            if self.state != "stopped" and self._thread and self._thread.is_alive():
                logger.info("[LISTENER] start() called but listener is already running.")
                return self.status()

            self.device_id = device_id
            self.wake_word_enabled = wake_word_enabled
            self.clap_enabled = clap_enabled
            self.errors = []
            self.warnings = []
            
            # Resolve device info
            dev_res = resolve_input_device(device_id)
            if not dev_res["ok"]:
                self.state = "error"
                self.errors.append(dev_res["fix"] or "Selected input device not found.")
                return self.status()
                
            self.device_name = dev_res["device_name"]
            
            # Calibration check (heard_signal check)
            if not force_start:
                try:
                    # Run a very brief 0.5s check to see if mic is alive
                    test_res = test_microphone(device_id=device_id, duration_seconds=0.5)
                    if not test_res.get("heard_signal", False):
                        self.state = "error"
                        self.errors.append("Microphone is not receiving any audio signals. Please run calibration.")
                        return self.status()
                except Exception as ex:
                    self.state = "error"
                    self.errors.append(f"Failed to test microphone on start: {ex}")
                    return self.status()

            # Anti-echo check for loopback device names
            if check_loopback_device(self.device_name):
                self.warnings.append(f"Warning: Selected device '{self.device_name}' is a loopback/stereo mix device. This may cause voice loops.")

            # Start thread
            self._stop_event.clear()
            self.state = "idle"
            self._thread = threading.Thread(target=self.run_loop, daemon=True)
            self._thread.start()
            
            logger.info("[LISTENER] Background listener thread started successfully.")
            event_bus.emit("voice.listener.started", self.status()["data"])
            return self.status()

    def stop(self) -> dict[str, Any]:
        """Gracefully stops the background listening thread."""
        logger.info("[LISTENER] stop() requested.")
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
            
        self.state = "stopped"
        logger.info("[LISTENER] Background listener stopped.")
        event_bus.emit("voice.listener.stopped", self.status()["data"])
        return self.status()

    def status(self) -> dict[str, Any]:
        """Returns the full listener status structured response."""
        settings = get_settings()
        return {
            "ok": len(self.errors) == 0,
            "data": {
                "enabled": settings.listener_enabled,
                "running": self.state != "stopped" and self._thread is not None and self._thread.is_alive(),
                "state": self.state,
                "device_id": str(self.device_id),
                "device_name": self.device_name,
                "wake_word_enabled": self.wake_word_enabled,
                "clap_enabled": self.clap_enabled,
                "last_trigger": self.last_trigger,
                "last_transcript": self.last_transcript,
                "last_ignored_reason": self.last_ignored_reason,
                "speaking": is_speaking_now(),
                "cooldown_until": datetime.fromtimestamp(self.cooldown_until).isoformat() if self.cooldown_until > 0 else None,
                "errors": list(self.errors),
                "warnings": list(self.warnings),
                "metrics": dict(self.metrics)
            }
        }

    def run_loop(self) -> None:
        """The continuous main loop running on the background thread."""
        settings = get_settings()
        self.state = "listening_for_trigger"
        event_bus.emit("voice.listener.state", {"state": self.state})

        while not self._stop_event.is_set():
            # Check rate limiting for trigger counts (max triggers per minute)
            now = time.time()
            self._trigger_timestamps = [t for t in self._trigger_timestamps if now - t < 60.0]
            if len(self._trigger_timestamps) >= settings.max_triggers_per_minute:
                logger.error("[LISTENER] Trigger rate limit hit! Shifting to cooldown.")
                self.warnings.append("Trigger rate limit exceeded. Lower speaker volume or clap sensitivity.")
                self.enter_cooldown("rate_limit_exceeded")
                time.sleep(1.0)
                continue

            # Ensure STT is configured
            stt_conf = stt_dependency_status(settings)
            if not stt_conf["configured"] and self.wake_word_enabled:
                self.state = "error"
                self.errors.append("STT is not configured but wake word is enabled. Add Vosk model.")
                event_bus.emit("voice.listener.state", {"state": self.state})
                break

            # If speaking or in active cooldown, sleep briefly and skip
            if is_speaking_now():
                if self.state != "speaking" and self.state != "cooldown":
                    self.state = "speaking"
                    event_bus.emit("voice.listener.state", {"state": self.state})
                time.sleep(0.1)
                continue
            else:
                if self.state in {"speaking", "cooldown"}:
                    self.state = "listening_for_trigger"
                    event_bus.emit("voice.listener.state", {"state": self.state})

            # Check if self-echo loop triggered in anti_echo
            from app.voice.anti_echo import _self_echo_loop_triggered
            if _self_echo_loop_triggered:
                self.state = "error"
                self.errors.append("Self-echo loop detected. Use headphones or lower speaker volume.")
                event_bus.emit("voice.listener.state", {"state": self.state})
                logger.error("[LISTENER] Self-echo loop detected. Stopping listener.")
                break

            try:
                # Continuous audio window capture
                self.process_audio_window()
            except Exception as e:
                logger.exception("[LISTENER] Error during process_audio_window: %s", e)
                time.sleep(0.5)

    def process_audio_window(self) -> None:
        """Captures a short window of audio to detect clap or wake words."""
        settings = get_settings()
        self.metrics["audio_windows"] += 1
        
        # Wake word requires 1.5s window, clap can be checked in the same window
        duration = 1.5
        try:
            capture = capture_audio(
                device_id=self.device_id,
                duration_seconds=duration,
                sample_rate=16000,
                channels=1
            )
        except VoiceDependencyError as ex:
            logger.error("[LISTENER] Audio capture failed: %s", ex)
            self.metrics["no_audio_events"] += 1
            time.sleep(0.5)
            return
        except Exception as ex:
            logger.error("[LISTENER] Audio capture exception: %s", ex)
            time.sleep(0.5)
            return

        # Check silent inputs
        if capture.rms < settings.min_rms_threshold:
            self.metrics["no_audio_events"] += 1
            return

        # Run trigger detection
        self.detect_trigger(capture)

    def detect_trigger(self, capture: Any) -> None:
        """Determines if a clap or wake-word was received."""
        settings = get_settings()
        
        # 1. Clap detection
        if self.clap_enabled:
            if capture.peak > settings.clap_threshold:
                logger.info("[LISTENER] Clap detected! peak=%.3f, threshold=%.3f", capture.peak, settings.clap_threshold)
                self.last_trigger = "clap"
                self._trigger_timestamps.append(time.time())
                self.metrics["triggers"] += 1
                self.state = "triggered"
                event_bus.emit("voice.listener.state", {"state": self.state})
                self.record_command_after_trigger()
                return

        # 2. Wake-word detection via STT transcription
        if self.wake_word_enabled:
            self.state = "transcribing"
            event_bus.emit("voice.listener.state", {"state": self.state})
            
            stt = STTService(settings)
            stt_res = stt.transcribe(capture)
            transcript = stt_res.get("transcript")
            
            if transcript:
                norm_t = transcript.lower()
                wake_keywords = [w.strip().lower() for w in settings.wake_words.split(",")]
                
                # Check for direct matches or substrings
                matched_word = None
                for kw in wake_keywords:
                    if kw in norm_t:
                        matched_word = kw
                        break
                        
                if matched_word:
                    logger.info("[LISTENER] Wake word '%s' detected in transcript: '%s'", matched_word, transcript)
                    self.last_trigger = f"wake_word:{matched_word}"
                    self._trigger_timestamps.append(time.time())
                    self.metrics["triggers"] += 1
                    self.state = "triggered"
                    event_bus.emit("voice.listener.state", {"state": self.state})
                    self.record_command_after_trigger()
                    return

            self.state = "listening_for_trigger"
            event_bus.emit("voice.listener.state", {"state": self.state})

    def record_command_after_trigger(self) -> None:
        """Triggers long command recording after finding a wake trigger."""
        settings = get_settings()
        self.state = "recording_command"
        event_bus.emit("voice.listener.state", {"state": self.state})
        
        rec_duration = settings.command_record_seconds
        logger.info("[LISTENER] Triggered! Recording full command for %ds...", rec_duration)
        
        try:
            capture = capture_audio(
                device_id=self.device_id,
                duration_seconds=rec_duration,
                sample_rate=16000,
                channels=1
            )
        except Exception as e:
            logger.error("[LISTENER] Failed to capture command audio: %s", e)
            self.state = "listening_for_trigger"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        # Handle empty/silent command recording
        if capture.rms < settings.min_rms_threshold:
            logger.warning("[LISTENER] Captured command was completely silent.")
            self.state = "listening_for_trigger"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        self.transcribe(capture)

    def transcribe(self, capture: Any) -> None:
        """Transcribes the captured command audio using STT."""
        settings = get_settings()
        self.state = "transcribing"
        event_bus.emit("voice.listener.state", {"state": self.state})
        
        stt = STTService(settings)
        stt_res = stt.transcribe(capture)
        transcript = stt_res.get("transcript")
        
        if not transcript:
            logger.info("[LISTENER] STT returned empty transcript for command.")
            self.state = "listening_for_trigger"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        logger.info("[LISTENER] Command transcript received: '%s'", transcript)
        self.last_transcript = transcript

        # Anti-echo guard checks
        guard_res = should_ignore_transcript(transcript)
        if guard_res["ignore"]:
            logger.warning("[LISTENER] Transcript ignored. Reason: %s", guard_res["reason"])
            self.last_ignored_reason = guard_res["reason"] or "echo"
            if guard_res["self_echo_blocked"]:
                self.metrics["ignored_self_audio"] += 1
            
            if guard_res["stop_listener"]:
                self.state = "error"
                self.errors.append("Self-echo loop detected. Lower speaker volume or use headphones.")
                event_bus.emit("voice.listener.state", {"state": self.state})
                self.stop()
            else:
                self.enter_cooldown("ignored_echo")
            return

        self.send_to_assistant(transcript)

    def send_to_assistant(self, transcript: str) -> None:
        """Submits the transcribed text command to the assistant orchestrator."""
        self.state = "sending_to_assistant"
        event_bus.emit("voice.listener.state", {"state": self.state})
        
        settings = get_settings()
        orchestrator = AssistantOrchestrator(settings)
        
        logger.info("[LISTENER] Submitting command to AssistantOrchestrator: '%s'", transcript)
        self.metrics["commands_sent"] += 1

        # Run async ask() method inside background thread synchronously
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # We want TTS to play dynamically
                response = loop.run_until_complete(
                    orchestrator.ask(transcript, speak=True, source="voice")
                )
                logger.info("[LISTENER] Assistant orchestrator response: '%s'", response.get("text", "")[:50])
            finally:
                loop.close()
        except Exception as e:
            logger.exception("[LISTENER] Error submitting command to assistant: %s", e)

        # Transition to speaking when TTS starts, and then cooldown.
        # But wait! mark_tts_started/mark_tts_completed inside tts playback already manages the speaking flag.
        # We can enter cooldown here or let the TTS complete callback do it!
        # Entering cooldown ensures we definitely unlock after command submission.
        self.enter_cooldown("command_completed")

    def enter_cooldown(self, reason: str) -> None:
        """Locks listener processing for a brief window."""
        self.state = "cooldown"
        event_bus.emit("voice.listener.state", {"state": self.state})
        
        settings = get_settings()
        cooldown_sec = float(settings.cooldown_ms) / 1000.0
        self.cooldown_until = time.time() + cooldown_sec
        logger.info("[LISTENER] Cooldown activated for %.1fs (Reason: %s)", cooldown_sec, reason)
        event_bus.emit("listener.cooldown.started", {"duration_ms": settings.cooldown_ms})
        
        time.sleep(cooldown_sec)
        
        self.state = "listening_for_trigger"
        event_bus.emit("voice.listener.state", {"state": self.state})


# Single global VoiceListener instance
voice_listener = VoiceListener()
