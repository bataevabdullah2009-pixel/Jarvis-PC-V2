import queue
import threading
import time
import logging
from typing import Any, NamedTuple

from app.events.websocket_bus import event_bus
from app.voice.speech_orchestrator import stop_all_audio
from app.voice import anti_echo

logger = logging.getLogger("jarvis.speech_queue")


class TTSTask(NamedTuple):
    command_id: str
    route: str
    text: str
    tts_service: Any
    created_at: float


class SpeechQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[TTSTask] = queue.Queue()
        self._lock = threading.Lock()
        self._current_task: TTSTask | None = None
        self._cancel_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def submit(self, command_id: str, route: str, text: str, tts_service: Any) -> None:
        """Submit a new TTS task. Cancels any active or pending tasks first."""
        logger.info("[QUEUE] Submitting new TTS task command_id=%s text='%s'", command_id, text[:50])

        # 1. Stop current audio playback immediately
        stop_all_audio()

        # 2. Cancel the current processing (signal cancellation)
        self._cancel_event.set()

        # 3. Clear the queue
        while not self._queue.empty():
            try:
                pending_task = self._queue.get_nowait()
                logger.info("[QUEUE] Cancelling pending task command_id=%s", pending_task.command_id)
                event_bus.emit("assistant.tts.cancelled", {"command_id": pending_task.command_id})
            except queue.Empty:
                break

        # If there is a current task that we are interrupting:
        with self._lock:
            if self._current_task:
                logger.info("[QUEUE] Cancelling active task command_id=%s", self._current_task.command_id)
                event_bus.emit("assistant.tts.cancelled", {"command_id": self._current_task.command_id})
                self._current_task = None

        # Reset cancel event for the new task
        self._cancel_event.clear()

        # 4. Enqueue the new task
        task = TTSTask(
            command_id=command_id,
            route=route,
            text=text,
            tts_service=tts_service,
            created_at=time.perf_counter(),
        )
        self._queue.put(task)

    def _worker_loop(self) -> None:
        while True:
            try:
                task = self._queue.get()
                self._process_task(task)
                self._queue.task_done()
            except Exception as e:
                logger.exception("[QUEUE] Exception in worker loop: %s", e)
                time.sleep(0.1)

    def _process_task(self, task: TTSTask) -> None:
        with self._lock:
            self._current_task = task
            self._cancel_event.clear()

        if self._cancel_event.is_set():
            logger.info("[QUEUE] Task command_id=%s was cancelled before processing", task.command_id)
            event_bus.emit("assistant.tts.cancelled", {"command_id": task.command_id})
            with self._lock:
                if self._current_task == task:
                    self._current_task = None
            return

        logger.info("[QUEUE] Starting TTS task command_id=%s", task.command_id)
        event_bus.emit("assistant.tts.started", {"command_id": task.command_id})
        anti_echo.mark_tts_started(task.text)

        started = time.perf_counter()
        try:
            # We call tts_service.speak with blocking=True to block the worker thread during active playback.
            # If a new submit arrives, stop_all_audio() interrupts winsound/pygame and self._cancel_event is set.
            result = task.tts_service.speak(task.text, dry_run=False, blocking=True)

            if self._cancel_event.is_set():
                logger.info("[QUEUE] Task command_id=%s was cancelled/interrupted during playback", task.command_id)
                event_bus.emit("assistant.tts.cancelled", {"command_id": task.command_id})
                anti_echo.mark_tts_failed(task.text, "cancelled")
                return

            latency_ms = result.get("latency_ms") or int((time.perf_counter() - started) * 1000)
            if result.get("ok"):
                logger.info("[QUEUE] TTS task command_id=%s completed successfully in %sms", task.command_id, latency_ms)
                anti_echo.mark_tts_completed(task.text)
                event_bus.emit(
                    "assistant.tts.completed",
                    {
                        "command_id": task.command_id,
                        "route": task.route,
                        "provider": result.get("provider"),
                        "status": result.get("status"),
                        "played": bool(result.get("played")),
                        "error": None,
                        "latency_ms": latency_ms,
                    },
                )
            else:
                logger.warning("[QUEUE] TTS task command_id=%s failed: %s", task.command_id, result.get("error"))
                anti_echo.mark_tts_failed(task.text, str(result.get("error", "TTS error")))
                event_bus.emit(
                    "assistant.tts.failed",
                    {
                        "command_id": task.command_id,
                        "route": task.route,
                        "provider": result.get("provider"),
                        "status": result.get("status"),
                        "played": False,
                        "error": result.get("error"),
                        "latency_ms": latency_ms,
                    },
                )
        except Exception as e:
            logger.exception("[QUEUE] Exception processing task command_id=%s", task.command_id)
            latency_ms = int((time.perf_counter() - started) * 1000)
            anti_echo.mark_tts_failed(task.text, str(e))
            event_bus.emit(
                "assistant.tts.failed",
                {
                    "command_id": task.command_id,
                    "route": task.route,
                    "provider": "unknown",
                    "status": "failed",
                    "played": False,
                    "error": str(e),
                    "latency_ms": latency_ms,
                },
            )
        finally:
            with self._lock:
                if self._current_task == task:
                    self._current_task = None


speech_queue = SpeechQueue()
