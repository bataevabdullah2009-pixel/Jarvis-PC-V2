from __future__ import annotations

import time
import logging
import asyncio
import threading
import traceback
from typing import Any, Dict, List
from datetime import datetime
from app.core.config import LOG_DIR, get_settings
from app.events.websocket_bus import event_bus
from app.voice.microphone import capture_audio, diagnose_microphone_error, resolve_input_device, test_microphone, VoiceDependencyError
from app.voice.stt import STTService, stt_dependency_status
from app.voice.anti_echo import (
    should_ignore_transcript,
    is_speaking_now,
    check_loopback_device,
    SELF_ECHO_FIX,
)
from app.voice.tts import TTSService
from app.voice.wakeword import extract_wake_command
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

        self.state = "stopped"
        self.device_id = "default"
        self.device_name = "Default Device"
        self.wake_word_enabled = True
        self.clap_enabled = False

        self.last_trigger = ""
        self.last_transcript = ""
        self.last_heard_text = ""
        self.last_wake_word = ""
        self.last_command_text = ""
        self.last_ignored_reason = ""
        self.last_error_type: str | None = None
        self.last_error: str | None = None
        self.fix: str | None = None
        self.cooldown_until = 0.0

        self.errors: list[str] = []
        self.warnings: list[str] = []

        # Metrics
        self.metrics = {
            "audio_windows": 0,
            "transcripts": 0,
            "triggers": 0,
            "wake_triggers": 0,
            "ignored_no_wake_word": 0,
            "commands_sent": 0,
            "ignored_self_audio": 0,
            "no_audio_events": 0,
            "self_echo_blocks": 0,
            "cooldown_blocks": 0,
            "stops_without_reason": 0,
        }

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._trigger_timestamps: list[float] = []
        self._assistant_lock = threading.Lock()
        self._last_opened_device: dict[str, Any] | None = None

        self._initialized = True

    def _inc_metric(self, key: str, amount: int = 1) -> None:
        self.metrics[key] = int(self.metrics.get(key, 0)) + amount

    def _write_crash_log(self, exc: BaseException) -> None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with (LOG_DIR / "listener.log").open("a", encoding="utf-8", newline="\n") as file:
                file.write(f"\n[{datetime.utcnow().isoformat()}Z] listener_thread_crashed\n")
                file.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:
            logger.exception("[LISTENER] Failed to write listener crash log")

    def _resolve_input_device(self, device_id: str = "default") -> dict[str, Any]:
        try:
            return resolve_input_device(get_settings(), device_id=device_id)
        except TypeError:
            return resolve_input_device(device_id)

    def check_safe_start(self, device_id: str = "default") -> dict[str, Any]:
        """
        Performs all gate checks required for safe listener startup.
        Returns a dict indicating if it's safe to start, the first failed check, the recommended fix, and all checks.
        """
        settings = get_settings()

        # 1. Backend alive
        backend_alive = True

        # 2. Selected device exists
        try:
            dev_res = self._resolve_input_device(device_id)
        except Exception as exc:
            message = str(exc)
            permission_markers = ("permission", "access", "denied", "privacy", "разреш")
            error_type = "microphone_permission_denied" if any(marker in message.lower() for marker in permission_markers) else "microphone_device_not_found"
            return {
                "safe_to_start": False,
                "failed_check": error_type,
                "fix": "Разрешите доступ к микрофону в настройках Windows и выберите рабочее устройство.",
                "checks": {"backend_alive": backend_alive, "device_exists": False},
            }
        device_exists = bool(dev_res.get("ok", False))

        # 3. Microphone probe. Startup verifies capture access, not speech/noise
        # in a tiny window; otherwise a quiet room blocks autolisten forever.
        microphone_ok = False
        microphone_heard_signal = False
        if device_exists:
            try:
                # Capture 0.2s duration (fast, non-blocking)
                test_res = test_microphone(device_id=device_id, duration_seconds=0.2)
                microphone_ok = bool(test_res.get("ok", True))
                microphone_heard_signal = bool(test_res.get("heard_signal", False))
                opened_device = test_res.get("opened_device")
                if isinstance(opened_device, dict):
                    self._last_opened_device = opened_device
            except Exception as e:
                logger.error("[LISTENER] Microphone test exception: %s", e)
                diagnosis = diagnose_microphone_error(e)
                self.last_error_type = diagnosis["error_type"]
                self.last_error = diagnosis["error"]
                self.fix = diagnosis["fixes"][0]
                microphone_ok = False

        # 4. STT configured
        stt_conf = stt_dependency_status(settings)
        stt_configured = bool(stt_conf.get("configured", False))

        # 5. Anti-echo available
        anti_echo_available = True

        # 6. No current TTS speaking and OpenRouter not busy
        from app.providers.openrouter import OpenRouterPlanner
        ai_busy = getattr(OpenRouterPlanner, "_busy", False)
        no_current_tts_speaking = not is_speaking_now() and not ai_busy

        # 7. No other listener running
        no_other_listener_running = self.state == "stopped" or self._thread is None or not self._thread.is_alive()

        checks = {
            "backend_alive": backend_alive,
            "device_exists": device_exists,
            "microphone_test": microphone_ok,
            "microphone_heard_signal": microphone_heard_signal,
            "stt_configured": stt_configured,
            "anti_echo_available": anti_echo_available,
            "no_current_tts_speaking": no_current_tts_speaking,
            "no_other_listener_running": no_other_listener_running
        }

        safe_to_start = all(
            [
                backend_alive,
                device_exists,
                microphone_ok,
                stt_configured,
                anti_echo_available,
                no_current_tts_speaking,
                no_other_listener_running,
            ]
        )
        failed_check = None
        fix = None

        if not safe_to_start:
            if not device_exists:
                failed_check = dev_res.get("error_type") or "microphone_device_not_found"
                fix = dev_res.get("fix") or f"Выбранное устройство '{device_id}' не найдено."
            elif not microphone_ok:
                failed_check = self.last_error_type or "microphone_open_failed"
                fix = "Микрофон выбран, но сигнал не слышен. Проверьте чувствительность Windows, разрешение микрофона и выбранное устройство."
            elif not stt_configured:
                offline = stt_conf.get("offline", {}) if isinstance(stt_conf, dict) else {}
                if offline.get("vosk_available") and not offline.get("model_configured"):
                    failed_check = "vosk_model_missing"
                    fix = "Укажите JARVIS_VOSK_MODEL_PATH на распакованную Vosk-модель."
                else:
                    failed_check = "stt_not_configured"
                    fix = "Установите Vosk и укажите путь к модели через JARVIS_VOSK_MODEL_PATH."
            elif not no_current_tts_speaking:
                failed_check = "anti_echo_locked"
                fix = "Подождите, пока ассистент договорит, затем listener сам вернется к прослушиванию."
            elif not no_other_listener_running:
                failed_check = "already_running"
                fix = "Listener уже запущен."

            return {
                "safe_to_start": False,
                "failed_check": failed_check,
                "fix": fix,
                "checks": checks
            }

        if not safe_to_start:
            if not device_exists:
                failed_check = "device_not_found"
                fix = dev_res.get("fix") or f"Выбранное устройство '{device_id}' не найдено."
            elif not microphone_ok:
                failed_check = "microphone_capture_failed"
                fix = "Выберите другой микрофон или включите доступ Windows к микрофону"
            elif not stt_configured:
                failed_check = "stt_not_configured"
                fix = "Проверьте путь JARVIS_VOSK_MODEL_PATH"
            elif not no_current_tts_speaking:
                failed_check = "tts_speaking"
                fix = "Пожалуйста, подождите, пока Джарвис договорит фразу."
            elif not no_other_listener_running:
                failed_check = "already_running"
                fix = "Слушатель уже запущен."

        return {
            "safe_to_start": safe_to_start,
            "failed_check": failed_check,
            "fix": fix,
            "checks": checks
        }

    def start(self, device_id: str = "default", wake_word_enabled: bool = True, clap_enabled: bool = False, force_start: bool = False) -> dict[str, Any]:
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

            # Resolve device info first
            dev_res = self._resolve_input_device(device_id)
            if not dev_res["ok"]:
                self.block(dev_res.get("error_type") or "microphone_device_not_found", dev_res["fix"], dev_res["fix"] or "Selected input device not found.")
                return self.status()

            self.device_id = str(dev_res.get("device_id") if dev_res.get("device_id") is not None else device_id)
            self.device_name = dev_res["device_name"]

            if clap_enabled:
                try:
                    clap_probe = test_microphone(device_id=device_id, duration_seconds=0.2)
                    if not bool(clap_probe.get("heard_signal", False)):
                        self.block(
                            "microphone_no_audio",
                            "Выберите другой микрофон или включите доступ Windows к микрофону",
                            "Selected microphone did not return an audible signal for clap detection.",
                        )
                        return {"ok": False, "data": self.status()["data"]}
                except Exception as exc:
                    self.block(
                        "microphone_capture_failed",
                        "Выберите другой микрофон или включите доступ Windows к микрофону",
                        str(exc),
                    )
                    return {"ok": False, "data": self.status()["data"]}

            # Safe Start Gate checks (always verified on starting)
            if not force_start:
                gate_res = self.check_safe_start(device_id)
                if not gate_res["safe_to_start"]:
                    self.block(
                        gate_res["failed_check"] or "listener_blocked",
                        gate_res["fix"],
                        gate_res["fix"] or f"Safety gate check failed: {gate_res['failed_check']}",
                    )
                    return {
                        "ok": False,
                        "data": {
                            "enabled": get_settings().listener_enabled,
                            "autostart": get_settings().listener_autostart,
                            "running": False,
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
                            "metrics": dict(self.metrics),
                            "safe_to_start": False,
                            "failed_check": gate_res["failed_check"],
                            "last_error_type": self.last_error_type,
                            "last_error": self.last_error,
                            "fix": gate_res["fix"],
                            "checks": gate_res["checks"]
                        }
                    }

            if self._last_opened_device:
                opened = self._last_opened_device
                opened_id = str(opened.get("id") or opened.get("device_id") or self.device_id)
                self.device_id = opened_id
                self.device_name = str(opened.get("name") or self.device_name)
                try:
                    from app.core.config import patch_settings

                    patch_settings(
                        {
                            "listener_device_id": opened_id,
                            "listener_device_name": self.device_name,
                            "listener_device_hostapi": str(opened.get("hostapi") or ""),
                            "listener_device_channels": int(opened.get("channels") or 1),
                            "listener_device_samplerate": int(float(opened.get("default_samplerate") or 16000)),
                        }
                    )
                except Exception as exc:
                    logger.warning("[LISTENER] Failed to persist opened microphone device: %s", exc)

            # Anti-echo check for loopback device names
            if check_loopback_device(self.device_name):
                self.warnings.append(f"Warning: Selected device '{self.device_name}' is a loopback/stereo mix device. This may cause voice loops.")

            # Start thread
            self._stop_event.clear()
            self.state = "starting"
            self._thread = threading.Thread(target=self.run_loop, daemon=True)
            self._thread.start()

            # Sync listener_state in wake.py
            try:
                from app.voice.wake import listener_state
                listener_state.running = True
                listener_state.wake_word_enabled = self.wake_word_enabled
                listener_state.clap_enabled = self.clap_enabled
                listener_state.device_id = str(self.device_id)
            except Exception as e:
                logger.error("[LISTENER] Failed to sync listener_state on start: %s", e)

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
        self.last_error_type = None
        self.last_error = None
        self.fix = None
        self.errors = []

        # Sync listener_state in wake.py
        try:
            from app.voice.wake import listener_state
            listener_state.running = False
            listener_state.wake_word_enabled = False
            listener_state.clap_enabled = False
        except Exception as e:
            logger.error("[LISTENER] Failed to sync listener_state on stop: %s", e)

        logger.info("[LISTENER] Background listener stopped.")
        event_bus.emit("voice.listener.stopped", self.status()["data"])
        return self.status()

    def block(self, reason: str, fix: str | None, error: str | None = None) -> dict[str, Any]:
        """Marks the listener as blocked without failing the backend."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.state = "blocked"
        self.last_error_type = reason
        self.last_error = error or reason
        self.fix = fix
        self.errors = [self.last_error]
        event_bus.emit("voice.listener.blocked", self.status()["data"])
        return self.status()

    def status(self) -> dict[str, Any]:
        """Returns the full listener status structured response."""
        settings = get_settings()
        running = self.state not in {"stopped", "blocked", "error"} and self._thread is not None and self._thread.is_alive()
        gate_res = {"safe_to_start": False, "failed_check": None, "fix": None, "checks": {}}
        if settings.listener_enabled and not running:
            gate_res = self.check_safe_start(self.device_id)
        elif running:
            gate_res = {"safe_to_start": True, "failed_check": None, "fix": None, "checks": {"listener_running": True}}

        display_state = self.state
        if not settings.listener_enabled and not running and self.state not in {"blocked", "error"}:
            display_state = "stopped"
        elif settings.listener_enabled and settings.listener_autostart and not running:
            display_state = "blocked"
            if gate_res.get("safe_to_start"):
                self._inc_metric("stops_without_reason")
                self.last_error_type = "listener_not_running"
                self.last_error = "Listener is enabled but no background worker is running."
                self.fix = "Restart the listener from UI or POST /voice/listener-start."
            elif gate_res.get("failed_check") and self.state == "stopped":
                self.last_error_type = gate_res["failed_check"]
                self.last_error = gate_res["fix"] or gate_res["failed_check"]
                self.fix = gate_res["fix"]
            elif not self.last_error_type:
                self._inc_metric("stops_without_reason")
                self.last_error_type = gate_res["failed_check"] or "listener_not_running"
                self.last_error = self.last_error or "Listener is enabled but no background worker is running."
                self.fix = self.fix or gate_res["fix"] or "Restart the listener from UI or POST /voice/listener-start."

        reason = None if settings.listener_enabled else "listener_disabled"
        status_device_id = str(self.device_id or settings.listener_device_id)
        if status_device_id == "default" and settings.listener_device_id:
            status_device_id = str(settings.listener_device_id)
        metric_keys = (
            "audio_windows",
            "transcripts",
            "wake_triggers",
            "ignored_no_wake_word",
            "commands_sent",
            "ignored_self_audio",
            "no_audio_events",
            "stops_without_reason",
            "self_echo_blocks",
            "cooldown_blocks",
        )
        metrics = {key: int(self.metrics.get(key, 0)) for key in metric_keys}

        return {
            "ok": True,
            "data": {
                "enabled": settings.listener_enabled,
                "autostart": settings.listener_autostart,
                "running": running,
                "state": display_state,
                "assistant_name": settings.assistant_name,
                "wake_words": list(settings.wake_words),
                "device_id": status_device_id,
                "device_name": self.device_name,
                "wake_word_enabled": self.wake_word_enabled,
                "clap_enabled": self.clap_enabled,
                "last_trigger": self.last_trigger,
                "last_transcript": self.last_transcript,
                "last_heard_text": self.last_heard_text,
                "last_wake_word": self.last_wake_word,
                "last_command_text": self.last_command_text,
                "last_ignored_reason": self.last_ignored_reason or None,
                "speaking": is_speaking_now(),
                "cooldown_until": datetime.fromtimestamp(self.cooldown_until).isoformat() if self.cooldown_until > 0 else None,
                "errors": list(self.errors),
                "warnings": list(self.warnings),
                "metrics": metrics,
                "reason": reason,
                "safe_to_start": gate_res["safe_to_start"],
                "failed_check": gate_res["failed_check"],
                "last_error_type": self.last_error_type or gate_res["failed_check"],
                "last_error": self.last_error,
                "fix": self.fix or gate_res["fix"],
                "checks": gate_res["checks"]
            }
        }

    def run_loop(self) -> None:
        """The continuous main loop running on the background thread."""
        settings = get_settings()
        self.state = "listening_for_wake_word"
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
                self.state = "blocked"
                self.last_error_type = "stt_not_configured"
                self.last_error = "STT is not configured but wake word is enabled. Add Vosk model."
                self.fix = "Укажите VOSK model path"
                self.errors.append(self.last_error)
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
                    self.state = "listening_for_wake_word"
                    event_bus.emit("voice.listener.state", {"state": self.state})

            # Check if self-echo loop triggered in anti_echo
            from app.voice.anti_echo import _self_echo_loop_triggered
            if _self_echo_loop_triggered:
                self.state = "blocked"
                self.last_error_type = "self_echo_detected"
                self.last_error = SELF_ECHO_FIX
                self.fix = SELF_ECHO_FIX
                self.errors.append(SELF_ECHO_FIX)
                event_bus.emit("voice.listener.state", {"state": self.state})
                logger.error("[LISTENER] Self-echo loop detected. Stopping listener.")
                break

            try:
                # Continuous audio window capture
                self.process_audio_window()
            except VoiceDependencyError as exc:
                details = exc.details if isinstance(exc.details, dict) else {}
                diagnosis = diagnose_microphone_error(exc)
                error_type = details.get("error_type") or diagnosis["error_type"]
                fixes = details.get("fixes") or diagnosis["fixes"]
                self.block(error_type, fixes[0] if fixes else str(exc), str(exc))
                break
            except Exception as e:
                logger.exception("[LISTENER] Error during process_audio_window: %s", e)
                self._write_crash_log(e)
                self.state = "error"
                self.last_error_type = "listener_thread_crashed"
                self.last_error = str(e)
                self.fix = "Откройте diagnostics/logs/listener.log, исправьте причину падения и перезапустите listener."
                self.errors.append(self.last_error)
                event_bus.emit("voice.listener.state", {"state": self.state})
                break

    def process_audio_window(self) -> None:
        """Captures a short window of audio to detect clap or wake words."""
        settings = get_settings()
        self._inc_metric("audio_windows")

        # Wake word requires 1.5s window, clap can be checked in the same window
        duration = 1.5
        try:
            capture = capture_audio(
                device_id=self.device_id,
                duration_seconds=duration,
                sample_rate=16000,
                channels=1
            )
            if isinstance(getattr(capture, "device", None), dict):
                opened = capture.device
                opened_id = str(opened.get("id") or opened.get("device_id") or self.device_id)
                if opened_id != str(self.device_id):
                    self.device_id = opened_id
                    self.device_name = str(opened.get("name") or self.device_name)
        except VoiceDependencyError as ex:
            logger.error("[LISTENER] Audio capture failed: %s", ex)
            self._inc_metric("no_audio_events")
            raise
        except Exception as ex:
            logger.error("[LISTENER] Audio capture exception: %s", ex)
            raise

        # Check silent inputs
        if capture.rms < settings.min_rms_threshold:
            self._inc_metric("no_audio_events")
            return

        # Run trigger detection
        self.detect_trigger(capture)

    def detect_trigger(self, capture: Any) -> None:
        """Transcribes one short audio window and gates assistant calls by wake word."""
        settings = get_settings()

        if not self.wake_word_enabled:
            self.last_ignored_reason = "wake_word_disabled"
            self.state = "listening_for_wake_word"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        self.state = "transcribing"
        event_bus.emit("voice.listener.state", {"state": self.state})

        stt = STTService(settings)
        stt_res = stt.transcribe(capture)
        transcript = (stt_res.get("transcript") or "").strip()
        if not transcript:
            self.state = "listening_for_wake_word"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        self._inc_metric("transcripts")
        self.last_transcript = transcript
        self.last_heard_text = transcript

        guard_res = should_ignore_transcript(transcript)
        if guard_res["ignore"]:
            self.last_ignored_reason = guard_res["reason"] or "self_audio"
            if guard_res["self_echo_blocked"]:
                self._inc_metric("ignored_self_audio")
                self._inc_metric("self_echo_blocks")
            if guard_res["reason"] == "speaking_active":
                self._inc_metric("cooldown_blocks")
            if guard_res["stop_listener"]:
                self.block("self_echo_detected", guard_res.get("fix") or SELF_ECHO_FIX, guard_res.get("fix") or SELF_ECHO_FIX)
            else:
                self.enter_cooldown("ignored_self_audio")
            return

        wake = extract_wake_command(transcript, list(settings.wake_words))
        self.last_ignored_reason = wake["reason"]
        if not wake["triggered"]:
            self._inc_metric("ignored_no_wake_word")
            self.state = "listening_for_wake_word"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        self.last_wake_word = wake["wake_word"] or ""
        self.last_command_text = wake["command_text"]
        self.last_trigger = f"wake_word:{self.last_wake_word}"
        self._trigger_timestamps.append(time.time())
        self._inc_metric("triggers")
        self._inc_metric("wake_triggers")
        self.state = "wake_word_detected"
        event_bus.emit("voice.listener.state", {"state": self.state})

        if not self.last_command_text:
            self.acknowledge_empty_wake()
            return

        self.send_to_assistant(self.last_command_text)

    def acknowledge_empty_wake(self) -> None:
        """Reply briefly to a bare wake word without sending an AI request."""
        settings = get_settings()
        address = settings.address()
        reply = f"Да, {address}?" if address else "Да?"
        try:
            self.state = "speaking"
            event_bus.emit("voice.listener.state", {"state": self.state})
            TTSService(settings).speak(reply, blocking=True)
        except Exception as exc:
            logger.warning("[LISTENER] Empty wake acknowledgement failed: %s", exc)
        finally:
            self.enter_cooldown("empty_wake_word")

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
            self.state = "listening_for_wake_word"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        # Handle empty/silent command recording
        if capture.rms < settings.min_rms_threshold:
            logger.warning("[LISTENER] Captured command was completely silent.")
            self.state = "listening_for_wake_word"
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
            self.state = "listening_for_wake_word"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        logger.info("[LISTENER] Command transcript received: '%s'", transcript)
        self.last_transcript = transcript
        self.last_heard_text = transcript

        # Anti-echo guard checks
        guard_res = should_ignore_transcript(transcript)
        if guard_res["ignore"]:
            logger.warning("[LISTENER] Transcript ignored. Reason: %s", guard_res["reason"])
            self.last_ignored_reason = guard_res["reason"] or "echo"
            if guard_res["self_echo_blocked"]:
                self._inc_metric("ignored_self_audio")

            if guard_res["stop_listener"]:
                self.state = "blocked"
                self.last_error_type = "self_echo_detected"
                self.last_error = guard_res.get("fix") or SELF_ECHO_FIX
                self.fix = guard_res.get("fix") or SELF_ECHO_FIX
                self.errors.append(self.last_error)
                event_bus.emit("voice.listener.state", {"state": self.state})
                self._stop_event.set()
            else:
                self.enter_cooldown("ignored_echo")
            return

        wake = extract_wake_command(str(transcript), list(settings.wake_words))
        self.last_ignored_reason = wake["reason"]
        if not wake["triggered"]:
            self._inc_metric("ignored_no_wake_word")
            self.state = "listening_for_wake_word"
            event_bus.emit("voice.listener.state", {"state": self.state})
            return

        self.last_wake_word = wake["wake_word"] or ""
        self.last_command_text = wake["command_text"]
        if not self.last_command_text:
            self.acknowledge_empty_wake()
            return

        self.send_to_assistant(self.last_command_text)

    def send_to_assistant(self, transcript: str) -> None:
        """Submits the transcribed text command to the assistant orchestrator."""
        self.state = "sending_to_assistant"
        event_bus.emit("voice.listener.state", {"state": self.state})

        if not self._assistant_lock.acquire(blocking=False):
            self.last_ignored_reason = "assistant_busy"
            self.enter_cooldown("assistant_busy")
            return

        settings = get_settings()
        orchestrator = AssistantOrchestrator(settings)

        logger.info("[LISTENER] Submitting command to AssistantOrchestrator: '%s'", transcript)
        self._inc_metric("commands_sent")

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
        finally:
            self._assistant_lock.release()

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
        self._inc_metric("cooldown_blocks")
        self.cooldown_until = time.time() + cooldown_sec
        logger.info("[LISTENER] Cooldown activated for %.1fs (Reason: %s)", cooldown_sec, reason)
        event_bus.emit("listener.cooldown.started", {"duration_ms": settings.cooldown_ms})

        time.sleep(cooldown_sec)

        self.state = "listening_for_wake_word"
        event_bus.emit("voice.listener.state", {"state": self.state})


# Single global VoiceListener instance
voice_listener = VoiceListener()
