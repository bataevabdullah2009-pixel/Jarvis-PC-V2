from __future__ import annotations

import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Any
from uuid import uuid4

from app.core.config import LOG_DIR, Settings
from app.core.logging import get_logger
from app.core.safety import SafetyService
from app.events.websocket_bus import event_bus
from app.pc.apps import open_app
from app.pc.browser import open_url
from app.router.ai_planner import AIPlanner
from app.router.intent_detector import match_open_app, match_scenario, normalize_text
from app.scenarios import music, news, welcome_home, workspace
from app.storage.command_store import get_commands
from app.voice.tts import TTSService


logger = get_logger(__name__)


def _pipeline_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pipe_logger = logging.getLogger("jarvis.assistant_pipeline")
    pipe_logger.setLevel(logging.INFO)
    pipe_logger.propagate = False
    if not any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "").endswith("assistant_pipeline.log")
        for handler in pipe_logger.handlers
    ):
        handler = RotatingFileHandler(LOG_DIR / "assistant_pipeline.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        pipe_logger.addHandler(handler)
    return pipe_logger


class CommandRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.safety = SafetyService(settings)
        self.ai_planner = AIPlanner(settings)
        self.tts = TTSService(settings)
        self._tts_wait = False
        self._openrouter_called = False
        self._local_matched = False

    def handle(self, text: str, *, source: str = "manual", context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        dry_run = bool(context.get("dry_run", False))
        self._tts_wait = bool(context.get("tts_wait", False) or context.get("wait_for_tts", False))
        self._openrouter_called = False
        self._local_matched = False
        command_id = f"cmd_{uuid4().hex[:12]}"
        started = time.perf_counter()
        normalized = normalize_text(text)
        pipeline_logger = _pipeline_logger()

        logger.info("command received id=%s source=%s normalized=%s", command_id, source, normalized)
        pipeline_logger.info("[PIPELINE] user_text=%s", text)
        pipeline_logger.info("[PIPELINE] mode=%s", self.settings.runtime_mode)
        event_bus.emit("assistant.command.received", {"command_id": command_id, "source": source})

        if not normalized:
            return self._finalize(
                command_id=command_id,
                route="validation",
                route_detail="validation:empty",
                provider="local",
                response_text="Сэр, команда пустая. Введите текст или повторите голосом.",
                actions=[],
                requires_confirmation=False,
                tts_dry_run=dry_run,
                started=started,
                router_ms=self._elapsed(started),
            )

        route_started = time.perf_counter()
        scenario_match = match_scenario(normalized)
        if scenario_match:
            self._local_matched = True
            result = self._run_scenario(scenario_match.name, dry_run=dry_run)
            router_ms = int((time.perf_counter() - route_started) * 1000)
            pipeline_logger.info("[PIPELINE] route=scenario")
            pipeline_logger.info("[PIPELINE] is_local=true")
            pipeline_logger.info("[PIPELINE] local_matched=true")
            pipeline_logger.info("[OPENROUTER] called=false reason=scenario")
            return self._finalize(
                command_id=command_id,
                route="scenario",
                route_detail=f"scenario:{scenario_match.name}",
                provider="local",
                response_text=result["response_text"],
                actions=result.get("actions", []),
                requires_confirmation=False,
                extra={"scenario": result, "scenario_name": scenario_match.name},
                tts_dry_run=dry_run,
                started=started,
                router_ms=router_ms,
            )

        local_command = self._match_local_command(normalized)
        if local_command:
            self._local_matched = True
            result = self._run_local_command(local_command, dry_run=dry_run)
            router_ms = int((time.perf_counter() - route_started) * 1000)
            pipeline_logger.info("[PIPELINE] route=local_command")
            pipeline_logger.info("[PIPELINE] is_local=true")
            pipeline_logger.info("[PIPELINE] local_matched=true")
            pipeline_logger.info("[OPENROUTER] called=false reason=local_command")
            return self._finalize(
                command_id=command_id,
                route="local_command",
                route_detail=f"local_command:{local_command.get('id', 'unknown')}",
                provider="local",
                response_text=result["response_text"],
                actions=result.get("actions", []),
                requires_confirmation=bool(result.get("requires_confirmation", False)),
                tts_dry_run=dry_run,
                started=started,
                router_ms=router_ms,
            )

        app_name = match_open_app(normalized)
        if app_name:
            self._local_matched = True
            action = {"type": "open_app", "target": app_name}
            decision = self.safety.validate(action)
            router_ms = int((time.perf_counter() - route_started) * 1000)
            pipeline_logger.info("[PIPELINE] route=local_command")
            pipeline_logger.info("[PIPELINE] is_local=true")
            pipeline_logger.info("[PIPELINE] local_matched=true")
            pipeline_logger.info("[OPENROUTER] called=false reason=open_app")
            if decision.requires_confirmation or decision.forbidden:
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail="local_command:open_app",
                    provider="local",
                    response_text=f"Сэр, действие требует подтверждения: открыть {app_name}.",
                    actions=[{**action, "safety": decision.to_dict()}],
                    requires_confirmation=decision.requires_confirmation,
                    forbidden=decision.forbidden,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=router_ms,
                )

            opened = open_app(app_name, self.settings, dry_run=dry_run)
            status_text = "Открываю, сэр." if opened["status"] in {"completed", "dry_run"} else opened.get("message", "Не удалось открыть приложение.")
            return self._finalize(
                command_id=command_id,
                route="local_command",
                route_detail="local_command:open_app",
                provider="local",
                response_text=status_text,
                actions=[opened],
                requires_confirmation=False,
                tts_dry_run=dry_run,
                started=started,
                router_ms=router_ms,
            )

        pipeline_logger.info("[PIPELINE] route=ai_fallback")
        pipeline_logger.info("[PIPELINE] is_local=false")
        pipeline_logger.info("[PIPELINE] local_matched=false")
        ai_started = time.perf_counter()
        plan = self.ai_planner.plan(text)
        self._openrouter_called = bool(plan.openrouter_called)
        ai_ms = plan.latency_ms if plan.latency_ms is not None else int((time.perf_counter() - ai_started) * 1000)
        pipeline_logger.info("[OPENROUTER] called=%s", plan.openrouter_called)
        pipeline_logger.info("[OPENROUTER] url=%s", plan.endpoint)
        pipeline_logger.info("[OPENROUTER] model=%s", plan.model or self.settings.openrouter_model)
        pipeline_logger.info("[OPENROUTER] status_code=%s", plan.status_code)
        pipeline_logger.info("[OPENROUTER] response_text_preview=%s", plan.response_text_preview)
        pipeline_logger.info("[OPENROUTER] raw_response_preview=%s", plan.raw_response_preview)
        pipeline_logger.info("[OPENROUTER] error=%s", plan.error_message or plan.error)
        if plan.status == "answered":
            return self._finalize(
                command_id=command_id,
                route="ai_fallback",
                route_detail="ai_fallback",
                provider=plan.provider,
                response_text=plan.answer_text,
                actions=plan.actions,
                requires_confirmation=False,
                extra={
                    "model": plan.model or self.settings.openrouter_model,
                    "plan": plan.to_dict(),
                },
                tts_dry_run=dry_run,
                started=started,
                router_ms=int((ai_started - route_started) * 1000),
                ai_ms=ai_ms,
            )

        return self._finalize(
            command_id=command_id,
            route="ai_fallback",
            route_detail="ai_fallback",
            provider=plan.provider,
            response_text=plan.answer_text,
            actions=[],
            requires_confirmation=False,
            forbidden=True,
            extra={
                "model": plan.model or self.settings.openrouter_model,
                "error": {
                    "type": plan.error_type or plan.error or "unknown",
                    "message": plan.error_message or plan.error or "unknown",
                    "fix": plan.fix,
                },
                "plan": plan.to_dict(),
            },
            tts_dry_run=dry_run,
            skip_tts=True,
            started=started,
            router_ms=int((ai_started - route_started) * 1000),
            ai_ms=ai_ms,
        )

    def _match_local_command(self, normalized_text: str) -> dict[str, Any] | None:
        for command in get_commands().get("commands", []):
            phrases = command.get("phrases") or command.get("triggers") or []
            normalized_phrases = {normalize_text(str(phrase)) for phrase in phrases}
            if normalized_text in normalized_phrases or any(phrase and phrase in normalized_text for phrase in normalized_phrases):
                return command
        return None

    def _run_local_command(self, command: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        action_type = str(command.get("action", "")).strip()
        value = str(command.get("value", "")).strip()

        if action_type == "open_app":
            opened = open_app(value, self.settings, dry_run=dry_run)
            return {"response_text": "Открываю, сэр.", "actions": [opened]}

        if action_type == "open_url":
            opened = open_url(value, dry_run=dry_run)
            return {"response_text": "Открываю, сэр.", "actions": [opened]}

        if action_type == "play_music_search":
            result = music.run(self.settings, dry_run=dry_run, query=value or "Back in Black")
            return {"response_text": result["response_text"], "actions": result.get("actions", [])}

        if action_type == "read_news":
            result = news.run(self.settings, dry_run=dry_run)
            return {"response_text": result["response_text"], "actions": result.get("actions", [])}

        if action_type == "respond_text":
            return {"response_text": value or "Привет, сэр. Я на связи.", "actions": []}

        if action_type == "scenario":
            result = self._run_scenario(value, dry_run=dry_run)
            return {"response_text": result["response_text"], "actions": result.get("actions", [])}

        if action_type in {"volume_up", "volume_down", "mute", "unmute", "screenshot"}:
            return {
                "response_text": "Команда принята, сэр.",
                "actions": [{"type": action_type, "target": value or "system", "status": "dry_run" if dry_run else "queued"}],
            }

        return {
            "response_text": "Сэр, команда найдена, но исполнитель для нее еще не настроен.",
            "actions": [{"type": action_type or "unknown", "target": value, "status": "not_implemented"}],
        }

    def _run_scenario(self, name: str, *, dry_run: bool) -> dict[str, Any]:
        if name == "welcome_home":
            return welcome_home.run(self.settings, dry_run=dry_run)
        if name == "news":
            return news.run(self.settings, dry_run=dry_run)
        if name == "workspace":
            return workspace.run(self.settings, dry_run=dry_run)
        if name == "music":
            return music.run(self.settings, dry_run=dry_run)
        raise ValueError(f"Unknown scenario: {name}")

    def _finalize(
        self,
        *,
        command_id: str,
        route: str,
        route_detail: str,
        provider: str,
        response_text: str,
        actions: list[dict[str, Any]],
        requires_confirmation: bool,
        started: float,
        router_ms: int,
        ai_ms: int = 0,
        forbidden: bool = False,
        extra: dict[str, Any] | None = None,
        tts_dry_run: bool = False,
        skip_tts: bool = False,
    ) -> dict[str, Any]:
        safe_text = (response_text or "").strip() or "Команда выполнена."
        tts_started = time.perf_counter()
        if skip_tts:
            tts_result = {
                "mode": "none",
                "provider": "none",
                "requested": False,
                "called": False,
                "spoken": False,
                "played": False,
                "ok": False,
                "audio_available": False,
                "status": "skipped",
                "status_code": None,
                "audio_bytes": 0,
                "fallback_used": False,
                "error": "Skipped because OpenRouter did not return speakable text.",
                "latency_ms": 0,
                "text": safe_text[:500],
            }
            tts_ms = 0
        else:
            tts_result = self.tts.speak(safe_text, dry_run=tts_dry_run)
            tts_ms = int((time.perf_counter() - tts_started) * 1000)
            if tts_result.get("latency_ms") is None:
                tts_result["latency_ms"] = tts_ms
        total_ms = int((time.perf_counter() - started) * 1000)
        status = "blocked" if forbidden else "requires_confirmation" if requires_confirmation else "completed"
        latency = {
            "router_ms": router_ms,
            "ai_ms": ai_ms,
            "tts_ms": int(tts_result.get("latency_ms") or tts_ms),
            "total_ms": total_ms,
        }
        result: dict[str, Any] = {
            "command_id": command_id,
            "ok": status == "completed",
            "status": status,
            "route": route,
            "route_detail": route_detail,
            "provider": provider,
            "model": extra.get("model") if extra else None,
            "openrouter_called": self._openrouter_called,
            "fish_audio_called": bool(tts_result.get("called", False)),
            "local_matched": self._local_matched,
            "runtime_mode": self.settings.runtime_mode,
            "handled": True,
            "executed": status == "completed",
            "action": route_detail.split(":", 1)[-1] if ":" in route_detail else route_detail,
            "text": safe_text,
            "response_text": safe_text,
            "spoken": bool(tts_result.get("spoken", False)),
            "tts": tts_result,
            "latency": latency,
            "actions": actions,
            "requires_confirmation": requires_confirmation,
        }
        if extra:
            result.update(extra)

        pipeline_logger = _pipeline_logger()
        pipeline_logger.info("[PIPELINE] route=%s", route)
        pipeline_logger.info("[PIPELINE] mode=%s", self.settings.runtime_mode)
        pipeline_logger.info("[PIPELINE] local_matched=%s", self._local_matched)
        pipeline_logger.info("[PIPELINE] provider=%s", provider)
        pipeline_logger.info("[OPENROUTER] called=%s", self._openrouter_called)
        plan_log = extra.get("plan") if extra else None
        pipeline_logger.info("[OPENROUTER] url=%s", plan_log.get("endpoint") if isinstance(plan_log, dict) else None)
        pipeline_logger.info("[OPENROUTER] model=%s", (plan_log.get("model") if isinstance(plan_log, dict) else None) or (extra.get("model") if extra else None))
        pipeline_logger.info("[OPENROUTER] status_code=%s", plan_log.get("status_code") if isinstance(plan_log, dict) else None)
        pipeline_logger.info("[OPENROUTER] response_text_preview=%s", plan_log.get("response_text_preview") if isinstance(plan_log, dict) else None)
        pipeline_logger.info("[OPENROUTER] raw_response_preview=%s", plan_log.get("raw_response_preview") if isinstance(plan_log, dict) else None)
        pipeline_logger.info("[OPENROUTER] error=%s", plan_log.get("error_message") or plan_log.get("error") if isinstance(plan_log, dict) else None)
        pipeline_logger.info("[FISH] called=%s", bool(tts_result.get("called", False)))
        pipeline_logger.info("[FISH] voice_id_present=%s", bool(self.settings.fish_audio_voice_id))
        pipeline_logger.info("[FISH] status_code=%s", tts_result.get("status_code"))
        pipeline_logger.info("[FISH] status=%s", tts_result.get("status"))
        pipeline_logger.info("[FISH] audio_bytes=%s", tts_result.get("audio_bytes"))
        pipeline_logger.info("[FISH] error=%s", tts_result.get("error"))
        pipeline_logger.info("[TTS] provider=%s", tts_result.get("provider"))
        pipeline_logger.info("[TTS] fallback_used=%s", tts_result.get("fallback_used"))
        pipeline_logger.info("[TTS] played=%s", tts_result.get("played"))
        pipeline_logger.info("[TTS] error=%s", tts_result.get("error"))

        event_bus.emit(
            "assistant.command.completed" if status == "completed" else "assistant.command.failed",
            {"command_id": command_id, "route": route, "route_detail": route_detail, "status": status},
        )
        logger.info("command finished id=%s route=%s status=%s", command_id, route_detail, status)
        return result

    def _queued_tts_result(self, text: str) -> dict[str, Any]:
        return {
            "mode": "none",
            "provider": "none",
            "requested": True,
            "called": False,
            "async": True,
            "spoken": False,
            "played": False,
            "ok": False,
            "audio_available": False,
            "pending_audio": True,
            "status": "queued",
            "status_code": None,
            "audio_bytes": 0,
            "fallback_used": False,
            "error": None,
            "latency_ms": 0,
            "text": text[:500],
        }

    def _run_tts_background(self, command_id: str, route: str, text: str) -> None:
        pipeline_logger = _pipeline_logger()
        started = time.perf_counter()
        pipeline_logger.info("[TTS] async_start command_id=%s provider=fish_audio", command_id)
        result = self.tts.speak(text, dry_run=False)
        latency_ms = result.get("latency_ms") or int((time.perf_counter() - started) * 1000)
        pipeline_logger.info(
            "[FISH] async command_id=%s status_code=%s latency_ms=%s audio_bytes=%s error=%s",
            command_id,
            result.get("status_code"),
            latency_ms,
            result.get("audio_bytes"),
            result.get("error"),
        )
        pipeline_logger.info(
            "[TTS] async_complete command_id=%s provider=%s fallback_used=%s played=%s error=%s",
            command_id,
            result.get("provider"),
            result.get("fallback_used"),
            result.get("played"),
            result.get("error"),
        )
        event_bus.emit(
            "assistant.tts.completed" if result.get("ok") else "assistant.tts.failed",
            {
                "command_id": command_id,
                "route": route,
                "provider": result.get("provider"),
                "status": result.get("status"),
                "played": bool(result.get("played")),
                "error": result.get("error"),
                "warning": result.get("warning"),
                "latency_ms": latency_ms,
            },
        )

    @staticmethod
    def _elapsed(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
