import queue
import threading
import time
import logging
from typing import Any, NamedTuple

from app.events.websocket_bus import event_bus
from app.voice.speech_orchestrator import stop_all_audio

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
        self._last_job_id: str | None = None
        self._last_job_status: str | None = None
        self._last_job_created_at: float | None = None
        self._last_provider: str | None = None
        self._last_error_type: str | None = None
        self._last_error: str | None = None
        self._last_result: dict[str, Any] | None = None
        self._last_played_at: float | None = None
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
                self._last_job_status = "cancelled"
                self._last_provider = self._last_provider or "text_only"
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
        with self._lock:
            self._last_job_id = command_id
            self._last_job_status = "queued"
            self._last_job_created_at = task.created_at
            self._last_provider = None
            self._last_error_type = None
            self._last_error = None
            self._last_result = None
            self._last_played_at = None
        event_bus.emit("tts.queued", {"job_id": command_id, "command_id": command_id, "route": route})
        event_bus.emit("assistant.tts.queued", {"command_id": command_id, "route": route})
        self._queue.put(task)

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = time.perf_counter()
            stuck_jobs: list[dict[str, Any]] = []
            if (
                self._last_job_id
                and self._last_job_status == "queued"
                and self._last_job_created_at is not None
                and now - self._last_job_created_at > 10
                and (not self._worker_thread or not self._worker_thread.is_alive())
            ):
                self._last_job_status = "failed"
                self._last_error_type = "tts_worker_not_active"
                self._last_error = "TTS job was queued longer than 10 seconds without an active worker."
            if (
                self._last_job_id
                and self._last_job_status == "queued"
                and self._last_job_created_at is not None
                and now - self._last_job_created_at > 10
            ):
                stuck_jobs.append(
                    {
                        "job_id": self._last_job_id,
                        "status": self._last_job_status,
                        "age_seconds": round(now - self._last_job_created_at, 3),
                    }
                )
            last_result = dict(self._last_result) if self._last_result else None
            if last_result and "audio" in last_result:
                last_result["audio"] = None
            return {
                "last_job_id": self._last_job_id,
                "last_job_status": self._last_job_status,
                "last_job_created_at": self._last_job_created_at,
                "last_job_age_seconds": (
                    now - self._last_job_created_at
                    if self._last_job_created_at is not None and self._last_job_status in {"queued", "started"}
                    else 0
                ),
                "last_provider": self._last_provider or "text_only",
                "last_error_type": self._last_error_type,
                "last_error": self._last_error,
                "last_played_at": self._last_played_at,
                "last_result": last_result,
                "queue_size": self._queue.qsize(),
                "active_job_id": self._current_task.command_id if self._current_task else None,
                "current_job_id": self._current_task.command_id if self._current_task else None,
                "stuck_jobs": stuck_jobs,
            }

    def reset(self) -> dict[str, Any]:
        stop_all_audio()
        self._cancel_event.set()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        with self._lock:
            self._current_task = None
            self._last_job_status = "failed"
            self._last_error_type = "queue_reset"
            self._last_error = "TTS queue was reset by user request."
            self._last_result = {
                "ok": False,
                "provider": self._last_provider or "text_only",
                "status": "failed",
                "error_type": "queue_reset",
                "error": self._last_error,
            }
        self._cancel_event.clear()
        event_bus.emit("tts.failed", {"status": "failed", "error_type": "queue_reset"})
        return self.status()

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
                self._last_job_status = "cancelled"
                self._last_provider = self._last_provider or "text_only"
                if self._current_task == task:
                    self._current_task = None
            return

        logger.info("[QUEUE] Starting TTS task command_id=%s", task.command_id)
        with self._lock:
            self._last_job_id = task.command_id
            self._last_job_status = "started"
        event_bus.emit("assistant.tts.started", {"command_id": task.command_id})
        event_bus.emit("tts.started", {"job_id": task.command_id, "command_id": task.command_id, "route": task.route})

        started = time.perf_counter()
        try:
            # We call tts_service.speak with blocking=True to block the worker thread during active playback.
            # If a new submit arrives, stop_all_audio() interrupts winsound/pygame and self._cancel_event is set.
            result = task.tts_service.speak(task.text, dry_run=False, blocking=True)

            if self._cancel_event.is_set():
                logger.info("[QUEUE] Task command_id=%s was cancelled/interrupted during playback", task.command_id)
                event_bus.emit("assistant.tts.cancelled", {"command_id": task.command_id})
                with self._lock:
                    self._last_job_status = "cancelled"
                    self._last_provider = result.get("provider") or "text_only"
                    self._last_result = {**result, "status": "cancelled"}
                return

            latency_ms = result.get("latency_ms") or int((time.perf_counter() - started) * 1000)
            if result.get("ok"):
                provider = result.get("provider") or "text_only"
                final_status = "played" if result.get("played") else "text_only"
                if provider == "text_only":
                    final_status = "text_only"
                with self._lock:
                    self._last_job_status = final_status
                    self._last_provider = provider
                    self._last_error_type = None
                    self._last_error = None
                    self._last_result = {**result, "status": final_status}
                    if result.get("played"):
                        self._last_played_at = time.time()
                logger.info("[QUEUE] TTS task command_id=%s completed successfully in %sms", task.command_id, latency_ms)
                event_bus.emit(
                    "tts.generated",
                    {
                        "job_id": task.command_id,
                        "command_id": task.command_id,
                        "route": task.route,
                        "provider": provider,
                        "status": final_status,
                        "audio_bytes": result.get("audio_bytes"),
                        "latency_ms": latency_ms,
                    },
                )
                if result.get("played"):
                    event_bus.emit(
                        "tts.played",
                        {
                            "job_id": task.command_id,
                            "command_id": task.command_id,
                            "route": task.route,
                            "provider": result.get("provider"),
                            "status": "played",
                            "latency_ms": latency_ms,
                        },
                    )
                event_bus.emit(
                    "assistant.tts.completed",
                    {
                        "command_id": task.command_id,
                        "route": task.route,
                        "provider": provider,
                        "status": final_status,
                        "played": bool(result.get("played")),
                        "error": None,
                        "latency_ms": latency_ms,
                    },
                )
            else:
                error_type = result.get("error_type") or result.get("status") or "tts_provider_error"
                error_message = result.get("error") or result.get("error_message") or "TTS provider failed."
                with self._lock:
                    self._last_job_status = "failed"
                    self._last_provider = result.get("provider") or "text_only"
                    self._last_error_type = error_type
                    self._last_error = error_message
                    self._last_result = {**result, "status": "failed", "error_type": error_type, "error": error_message}
                logger.warning("[QUEUE] TTS task command_id=%s failed: %s", task.command_id, error_message)
                event_bus.emit(
                    "tts.failed",
                    {
                        "job_id": task.command_id,
                        "command_id": task.command_id,
                        "route": task.route,
                        "provider": result.get("provider") or "text_only",
                        "status": "failed",
                        "error_type": error_type,
                        "error": error_message,
                        "latency_ms": latency_ms,
                    },
                )
                event_bus.emit(
                    "assistant.tts.failed",
                    {
                        "command_id": task.command_id,
                        "route": task.route,
                        "provider": result.get("provider") or "text_only",
                        "status": result.get("status"),
                        "played": False,
                        "error": error_message,
                        "latency_ms": latency_ms,
                    },
                )
        except Exception as e:
            logger.exception("[QUEUE] Exception processing task command_id=%s", task.command_id)
            latency_ms = int((time.perf_counter() - started) * 1000)
            with self._lock:
                self._last_job_status = "failed"
                self._last_provider = "text_only"
                self._last_error_type = e.__class__.__name__
                self._last_error = str(e)
                self._last_result = {
                    "ok": False,
                    "provider": "text_only",
                    "status": "failed",
                    "error_type": e.__class__.__name__,
                    "error": str(e),
                    "latency_ms": latency_ms,
                }
            event_bus.emit(
                "tts.failed",
                {
                    "job_id": task.command_id,
                    "command_id": task.command_id,
                    "route": task.route,
                    "provider": "text_only",
                    "status": "failed",
                    "error_type": e.__class__.__name__,
                    "error": str(e),
                    "latency_ms": latency_ms,
                },
            )
            event_bus.emit(
                "assistant.tts.failed",
                {
                    "command_id": task.command_id,
                    "route": task.route,
                    "provider": "text_only",
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
