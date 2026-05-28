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
from app.core.action_policy import ActionPolicy
from app.core.pending_confirmation import pending_store
from app.features.reminders import reminder_service


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
        self._skip_tts = not context.get("speak", True)
        self._openrouter_called = False
        self._local_matched = False
        command_id = f"cmd_{uuid4().hex[:12]}"
        started = time.perf_counter()
        pipeline_logger = _pipeline_logger()

        intent_started = time.perf_counter()
        normalized = normalize_text(text)

        logger.info("command received id=%s source=%s normalized=%s", command_id, source, normalized)
        pipeline_logger.info("[PIPELINE] user_text=%s", text)
        pipeline_logger.info("[PIPELINE] mode=%s", self.settings.runtime_mode)
        event_bus.emit("assistant.command.received", {"command_id": command_id, "source": source})

        if not normalized:
            intent_ms = int((time.perf_counter() - intent_started) * 1000)
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
                intent_ms=intent_ms,
            )

        # 1. Parse local reminders
        if "напомни" in normalized or "таймер" in normalized:
            try:
                parsed_rem = reminder_service.parse_and_create(text)
                if parsed_rem:
                    resp_text = f"Готово, сэр. Напомню через {int(parsed_rem['due_timestamp'] - time.time()) // 60 or 1} минут."
                    intent_ms = int((time.perf_counter() - intent_started) * 1000)
                    self._local_matched = True
                    return self._finalize(
                        command_id=command_id,
                        route="local_command",
                        route_detail="local_command:reminder",
                        provider="local",
                        response_text=resp_text,
                        actions=[parsed_rem],
                        requires_confirmation=False,
                        tts_dry_run=dry_run,
                        started=started,
                        router_ms=self._elapsed(started),
                        intent_ms=intent_ms,
                    )
            except Exception as e:
                logger.exception("Failed to parse reminder")

        # 2. Check pending confirmation actions first
        pending = pending_store.get_pending()
        if pending:
            if ActionPolicy.is_confirmation_intent(normalized):
                action = pending["action"]
                summary = pending["summary"]
                pending_store.clear_pending()
                
                action_type = action.get("type", "")
                target = action.get("target", "")
                
                executed_actions = []
                response_text = f"Выполняю, сэр: {summary}."
                
                if action_type == "open_app":
                    opened = open_app(target, self.settings, dry_run=dry_run)
                    executed_actions.append(opened)
                    if opened.get("status") in {"completed", "dry_run"}:
                        response_text = f"Приложение {target} успешно открыто, сэр."
                    else:
                        response_text = f"Не удалось открыть приложение {target}, сэр. Ошибка: {opened.get('message', 'unknown')}"
                elif action_type == "open_url":
                    opened = open_url(target, dry_run=dry_run)
                    executed_actions.append(opened)
                    response_text = f"Открываю ссылку в браузере, сэр."
                else:
                    action_completed = {**action, "status": "dry_run" if dry_run else "completed"}
                    executed_actions.append(action_completed)
                    
                intent_ms = int((time.perf_counter() - intent_started) * 1000)
                self._local_matched = True
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail=f"confirmed:{action_type}",
                    provider="local",
                    response_text=response_text,
                    actions=executed_actions,
                    requires_confirmation=False,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=self._elapsed(started),
                    intent_ms=intent_ms,
                )
            
            elif ActionPolicy.is_cancellation_intent(normalized):
                pending_store.clear_pending()
                intent_ms = int((time.perf_counter() - intent_started) * 1000)
                self._local_matched = True
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail="canceled:action",
                    provider="local",
                    response_text="Действие отменено, сэр.",
                    actions=[],
                    requires_confirmation=False,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=self._elapsed(started),
                    intent_ms=intent_ms,
                )

        # 3. Check for out-of-turn or expired confirmations
        if ActionPolicy.is_confirmation_intent(normalized):
            if pending_store.is_expired():
                pending_store.clear_pending()
                intent_ms = int((time.perf_counter() - intent_started) * 1000)
                self._local_matched = True
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail="validation:expired",
                    provider="local",
                    response_text="Сэр, подтверждение истекло. Повторите команду.",
                    actions=[],
                    requires_confirmation=False,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=self._elapsed(started),
                    intent_ms=intent_ms,
                )
            else:
                intent_ms = int((time.perf_counter() - intent_started) * 1000)
                self._local_matched = True
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail="validation:no_pending",
                    provider="local",
                    response_text="Сэр, сейчас нет действия, ожидающего подтверждения.",
                    actions=[],
                    requires_confirmation=False,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=self._elapsed(started),
                    intent_ms=intent_ms,
                )

        scenario_match = match_scenario(normalized)
        if scenario_match:
            self._local_matched = True
            intent_ms = int((time.perf_counter() - intent_started) * 1000)
            
            local_started = time.perf_counter()
            result = self._run_scenario(scenario_match.name, dry_run=dry_run)
            local_command_ms = int((time.perf_counter() - local_started) * 1000)
            
            router_ms = intent_ms
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
                intent_ms=intent_ms,
                local_command_ms=local_command_ms,
            )

        local_command = self._match_local_command(normalized)
        if local_command:
            self._local_matched = True
            intent_ms = int((time.perf_counter() - intent_started) * 1000)
            
            action_type = str(local_command.get("action_type") or local_command.get("action") or "").strip()
            value = str(local_command.get("action_value") or local_command.get("value") or "").strip()
            action = {"type": action_type, "target": value}
            
            if bool(local_command.get("confirm_required")):
                status, reason = "CONFIRM_REQUIRED", "command requires user confirmation"
            else:
                status, reason = ActionPolicy.classify_action(action)
            if status == "FORBIDDEN":
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail=f"forbidden:{action_type}",
                    provider="local",
                    response_text=f"Сэр, это действие заблокировано: {reason}",
                    actions=[],
                    requires_confirmation=False,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=intent_ms,
                    intent_ms=intent_ms,
                )
            elif status == "CONFIRM_REQUIRED":
                summary = f"выполнить команду '{local_command.get('phrases', [normalized])[0]}'"
                pending_store.set_pending(action, summary)
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail=f"pending:{action_type}",
                    provider="local",
                    response_text=f"Сэр, действие требует подтверждения: {summary}. Подтверждаете?",
                    actions=[action],
                    requires_confirmation=True,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=intent_ms,
                    intent_ms=intent_ms,
                )

            local_started = time.perf_counter()
            result = self._run_local_command(local_command, dry_run=dry_run)
            local_command_ms = int((time.perf_counter() - local_started) * 1000)
            
            router_ms = intent_ms
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
                requires_confirmation=False,
                tts_dry_run=dry_run,
                started=started,
                router_ms=router_ms,
                intent_ms=intent_ms,
                local_command_ms=local_command_ms,
            )

        app_name = match_open_app(normalized)
        if app_name:
            self._local_matched = True
            intent_ms = int((time.perf_counter() - intent_started) * 1000)
            action = {"type": "open_app", "target": app_name}
            
            status, reason = ActionPolicy.classify_action(action)
            if status == "FORBIDDEN":
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail="forbidden:open_app",
                    provider="local",
                    response_text=f"Сэр, это действие заблокировано: {reason}",
                    actions=[],
                    requires_confirmation=False,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=intent_ms,
                    intent_ms=intent_ms,
                )
            elif status == "CONFIRM_REQUIRED":
                summary = f"открыть приложение '{app_name}'"
                pending_store.set_pending(action, summary)
                return self._finalize(
                    command_id=command_id,
                    route="local_command",
                    route_detail="pending:open_app",
                    provider="local",
                    response_text=f"Сэр, открытие этого приложения требует подтверждения. Подтверждаете?",
                    actions=[action],
                    requires_confirmation=True,
                    tts_dry_run=dry_run,
                    started=started,
                    router_ms=intent_ms,
                    intent_ms=intent_ms,
                )

            local_started = time.perf_counter()
            opened = open_app(app_name, self.settings, dry_run=dry_run)
            local_command_ms = int((time.perf_counter() - local_started) * 1000)
            status_text = "Открываю, сэр." if opened["status"] in {"completed", "dry_run"} else opened.get("message", "Не удалось открыть приложение.")
            
            router_ms = intent_ms
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
                intent_ms=intent_ms,
                local_command_ms=local_command_ms,
            )

        # AI fallback path: no local command matched
        intent_ms = int((time.perf_counter() - intent_started) * 1000)
        pipeline_logger.info("[PIPELINE] route=ai_fallback")
        pipeline_logger.info("[PIPELINE] is_local=false")
        pipeline_logger.info("[PIPELINE] local_matched=false")
        
        ai_started = time.perf_counter()
        try:
            plan = self.ai_planner.plan(text, context)
        except TypeError:
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
        
        if plan.status in {"answered", "fallback"}:
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
                router_ms=intent_ms,
                ai_ms=ai_ms,
                intent_ms=intent_ms,
                openrouter_ms=ai_ms,
            )

        fallback_ans = plan.answer_text or "Сэр, AI-мозг пока недоступен, но локальные команды работают."
        if plan.status not in {"answered", "fallback"}:
            if plan.status in {"ai_limited", "ai_error"}:
                fallback_ans = plan.answer_text
            else:
                fallback_ans = "Сэр, AI-мозг пока недоступен, но локальные команды работают."

        route_detail = "ai_fallback"
        if plan.status == "ai_error":
            route_detail = "ai_fallback:unavailable"
        elif plan.status == "ai_limited":
            route_detail = "ai_fallback:missing_key"
        elif plan.status not in {"answered", "fallback"}:
            route_detail = "ai_fallback:unavailable"

        return self._finalize(
            command_id=command_id,
            route="ai_fallback",
            route_detail=route_detail,
            provider=plan.provider,
            response_text=fallback_ans,
            actions=[],
            requires_confirmation=False,
            forbidden=False,
            extra={
                "model": plan.model or self.settings.openrouter_model,
                "error": {
                    "type": plan.error_type or plan.error or "unknown",
                    "message": plan.error_message or plan.error or "unknown",
                    "fix": plan.fix or "Проверьте подключение к интернету или API-ключ OpenRouter в .env.",
                },
                "plan": plan.to_dict(),
            },
            tts_dry_run=dry_run,
            skip_tts=False,
            started=started,
            router_ms=intent_ms,
            ai_ms=ai_ms,
            intent_ms=intent_ms,
            openrouter_ms=ai_ms,
        )

    def _match_local_command(self, normalized_text: str) -> dict[str, Any] | None:
        for command in get_commands().get("commands", []):
            if command.get("enabled") is False:
                continue
            phrases = command.get("phrases") or command.get("triggers") or []
            normalized_phrases = {normalize_text(str(phrase)) for phrase in phrases}
            if normalized_text in normalized_phrases or any(phrase and phrase in normalized_text for phrase in normalized_phrases):
                return command
        return None

    def _run_local_command(self, command: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        action_type = str(command.get("action_type") or command.get("action") or "").strip()
        value = str(command.get("action_value") or command.get("value") or "").strip()

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

        if action_type in {"respond_text", "speak"}:
            return {"response_text": value or "Привет, сэр. Я на связи.", "actions": []}

        if action_type == "run_shell":
            return {
                "response_text": "Сэр, shell-команда требует подтверждения перед выполнением.",
                "actions": [{"type": "run_shell", "target": value, "status": "requires_confirmation"}],
            }

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
        intent_ms: int = 0,
        local_command_ms: int = 0,
        openrouter_ms: int = 0,
    ) -> dict[str, Any]:
        safe_text = (response_text or "").strip() or "Команда выполнена."
        address = self.settings.address()
        if address != "сэр":
            if address:
                safe_text = safe_text.replace("сэр", address).replace("Сэр", address.capitalize())
            else:
                safe_text = safe_text.replace(", сэр", "").replace("Сэр, ", "").replace(" сэр", "")
        tts_started = time.perf_counter()

        skip_tts = skip_tts or self._skip_tts
        tts_enqueue_ms = 0
        tts_generate_ms = 0
        tts_playback_started_ms = 0
        tts_ms = 0

        if skip_tts:
            tts_result = {
                "mode": "text_only",
                "provider": "text_only",
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
                "error": "Skipped because speak was disabled.",
                "error_type": "tts_skipped",
                "latency_ms": 0,
                "text": safe_text[:500],
            }
        elif not self._tts_wait and not tts_dry_run:
            tts_result = self._queued_tts_result(safe_text)
            enqueue_started = time.perf_counter()
            
            from app.voice.speech_queue import speech_queue
            speech_queue.submit(command_id, route, safe_text, self.tts)
            
            tts_enqueue_ms = int((time.perf_counter() - enqueue_started) * 1000)
        else:
            # Synchronous generate & playback
            tts_result = self.tts.speak(safe_text, dry_run=tts_dry_run, blocking=not tts_dry_run)
            tts_ms = int((time.perf_counter() - tts_started) * 1000)
            if tts_result.get("latency_ms") is None:
                tts_result["latency_ms"] = tts_ms
            
            tts_generate_ms = tts_result["latency_ms"]
            tts_playback_started_ms = tts_generate_ms

        total_response_ms = int((time.perf_counter() - started) * 1000)
        status = "blocked" if forbidden else "requires_confirmation" if requires_confirmation else "completed"
        
        latency = {
            "router_ms": router_ms,
            "ai_ms": ai_ms,
            "tts_ms": int(tts_result.get("latency_ms") or tts_ms),
            "total_ms": total_response_ms,
            "intent_ms": intent_ms,
            "local_command_ms": local_command_ms,
            "openrouter_ms": openrouter_ms,
            "tts_enqueue_ms": tts_enqueue_ms,
            "tts_generate_ms": tts_generate_ms,
            "tts_playback_started_ms": tts_playback_started_ms,
            "total_response_ms": total_response_ms
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
        provider = "fish_audio" if self.settings.fish_audio_api_key and self.settings.fish_audio_voice_id else "text_only"
        return {
            "mode": provider,
            "provider": provider,
            "requested": True,
            "called": False,
            "async": True,
            "spoken": False,
            "played": False,
            "ok": True,
            "audio_available": False,
            "pending_audio": True,
            "status": "queued",
            "status_code": None,
            "audio_bytes": 0,
            "fallback_used": False,
            "error": None,
            "error_type": None,
            "latency_ms": 0,
            "text": text[:500],
        }

    @staticmethod
    def _elapsed(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
