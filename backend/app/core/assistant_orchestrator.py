from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from typing import Any
from uuid import uuid4
import anyio

from app.core.config import LOG_DIR, Settings
from app.router.command_router import CommandRouter
from app.voice.tts import TTSService


def _get_backend_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("jarvis.backend")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "").endswith("jarvis-backend.log")
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(LOG_DIR / "jarvis-backend.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    return logger


class AssistantOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.router = CommandRouter(settings)
        self.tts = TTSService(settings)
        self.logger = _get_backend_logger()

    async def ask(
        self,
        text: str,
        speak: bool = True,
        source: str = "hud",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        context = context or {}
        context["dry_run"] = context.get("dry_run", False)
        context["speak"] = speak
        context["wait_for_tts"] = bool(context.get("wait_for_tts", False))

        # 1. Receive text
        text_val = (text or "").strip()
        self.logger.info("Assistant request (ask) received: input='%s' speak=%s source=%s", text_val, speak, source)

        # 2. If empty text - return controlled error response without crashing
        if not text_val:
            total_ms = int((time.perf_counter() - started) * 1000)
            err_response = {
                "ok": False,
                "mode": "error",
                "route": "validation",
                "route_detail": "validation:empty",
                "input": "",
                "text": "Сэр, запрос пустой. Задайте вопрос или произнесите команду.",
                "response_text": "Сэр, запрос пустой. Задайте вопрос или произнесите команду.",
                "spoken": False,
                "tts": {
                    "ok": False,
                    "provider": "none",
                    "spoken": False,
                    "played": False,
                    "error": "Empty input text",
                    "status": "failed",
                    "latency_ms": 0,
                    "text": "Сэр, запрос пустой. Задайте вопрос или произнесите команду."
                },
                "provider": "none",
                "model": "",
                "local_matched": False,
                "openrouter_called": False,
                "fish_audio_called": False,
                "error": {"code": "EMPTY_INPUT", "message": "Input text is empty"},
                "latency": {
                    "router_ms": 0,
                    "ai_ms": 0,
                    "tts_ms": 0,
                    "total_ms": total_ms
                },
                "actions": [],
                "requires_confirmation": False,
                "command_id": f"cmd_{uuid4().hex[:12]}",
                "status": "failed",
                "handled": False,
                "executed": False
            }
            return err_response

        try:
            # 3. Offload synchronous CommandRouter pipeline to thread pool
            def _run():
                return self.router.handle(text_val, source=source, context=context)

            router_result = await anyio.to_thread.run_sync(_run)
        except Exception as e:
            self.logger.exception("Exception inside CommandRouter.handle")
            total_ms = int((time.perf_counter() - started) * 1000)
            err_response = {
                "ok": False,
                "mode": "error",
                "route": "error",
                "route_detail": "error:crash",
                "input": text_val,
                "text": f"Сэр, произошел системный сбой: {str(e)}",
                "response_text": f"Сэр, произошел системный сбой: {str(e)}",
                "spoken": False,
                "tts": {
                    "ok": False,
                    "provider": "none",
                    "spoken": False,
                    "played": False,
                    "error": str(e),
                    "status": "failed",
                    "latency_ms": 0,
                    "text": f"Сэр, произошел системный сбой: {str(e)}"
                },
                "provider": "none",
                "model": "",
                "local_matched": False,
                "openrouter_called": False,
                "fish_audio_called": False,
                "error": {"code": "ROUTER_CRASH", "message": str(e)},
                "latency": {
                    "router_ms": 0,
                    "ai_ms": 0,
                    "tts_ms": 0,
                    "total_ms": total_ms
                },
                "actions": [],
                "requires_confirmation": False,
                "command_id": f"cmd_{uuid4().hex[:12]}",
                "status": "failed",
                "handled": False,
                "executed": False
            }
            return err_response

        # 4. Check if local command matched
        local_matched = bool(router_result.get("local_matched", False))

        # 5. Check if it's a controlled fallback (missing OpenRouter key and not local matched)
        has_openrouter_key = bool(self.settings.openrouter_api_key)
        
        # Determine mode
        route = router_result.get("route")
        provider = router_result.get("provider", "none")
        
        plan_data = router_result.get("plan", {})
        plan_status = plan_data.get("status") if isinstance(plan_data, dict) else None
        is_ai_error = (plan_status == "ai_error") or (router_result.get("route_detail") == "ai_fallback:unavailable" and has_openrouter_key)

        # Explicitly check for controlled fallback when key is missing and no local match occurred
        if not has_openrouter_key and not local_matched:
            fallback_text = "Сэр, AI-мозг пока не подключён: отсутствует OpenRouter API key. Локальные команды работают."
            router_result["text"] = fallback_text
            router_result["response_text"] = fallback_text
            router_result["provider"] = "none"
            router_result["route"] = "ai_fallback"
            router_result["route_detail"] = "ai_fallback:missing_key"
            
            # Speak fallback text if speak is requested
            if speak:
                if context.get("wait_for_tts"):
                    def _speak():
                        return self.tts.speak(fallback_text, dry_run=context.get("dry_run", False))
                    tts_res = await anyio.to_thread.run_sync(_speak)
                    router_result["tts"] = tts_res
                    router_result["spoken"] = bool(tts_res.get("spoken", False))
                    router_result["fish_audio_called"] = bool(tts_res.get("called", False) and tts_res.get("provider") == "fish_audio")
                else:
                    from app.voice.speech_queue import speech_queue
                    command_id = router_result.get("command_id") or f"cmd_{uuid4().hex[:12]}"
                    speech_queue.submit(command_id, "ai_fallback", fallback_text, self.tts)
                    tts_res = {
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
                        "text": fallback_text[:500],
                    }
                    router_result["tts"] = tts_res
                    router_result["spoken"] = False
                    router_result["fish_audio_called"] = False
            else:
                router_result["spoken"] = False
                router_result["fish_audio_called"] = False
                
            mode = "ai_limited"
        else:
            if local_matched:
                mode = "local"
            elif is_ai_error:
                mode = "ai_error"
                # Enrich error structure
                err_type = plan_data.get("error_type") or plan_data.get("error") or "provider_error"
                err_msg = plan_data.get("error_message") or plan_data.get("error") or "OpenRouter error occurred"
                err_fix = plan_data.get("fix") or "Проверьте подключение к интернету или API-ключ OpenRouter в .env."
                
                router_result["error"] = {
                    "code": "AI_ERROR",
                    "type": err_type,
                    "message": err_msg,
                    "fix": err_fix
                }
                router_result["openrouter_called"] = True
                
                # Make sure the text is correct human error text
                human_err_text = plan_data.get("answer_text") or router_result.get("text")
                router_result["text"] = human_err_text
                router_result["response_text"] = human_err_text
            elif provider in {"fallback", "none"} or route == "validation" or str(router_result.get("route_detail", "")).startswith("ai_fallback:unavailable"):
                mode = "ai_limited"
            else:
                mode = "ai"

        # 10. If voice failed (spoken is False but speak was True) - adjust mode or make sure it's clean
        spoken = bool(router_result.get("spoken", False))
        tts_info = router_result.get("tts", {})
        
        # If tts ok is false or provider is text_only, fallback happened correctly without crash
        if speak and not spoken and tts_info.get("provider") == "text_only":
            # The system fell back to text-only mode
            pass

        # Final envelope fields merging
        total_ms = int((time.perf_counter() - started) * 1000)
        latency = router_result.get("latency", {})
        if not latency:
            latency = {
                "router_ms": total_ms,
                "ai_ms": 0,
                "tts_ms": int(tts_info.get("latency_ms", 0)),
                "total_ms": total_ms
            }
        else:
            latency["total_ms"] = total_ms

        response = {
            "ok": router_result.get("ok", True),
            "mode": mode,
            "route": router_result.get("route", "unknown"),
            "route_detail": router_result.get("route_detail", "unknown"),
            "input": text_val,
            "text": router_result.get("response_text", router_result.get("text", "")),
            "response_text": router_result.get("response_text", router_result.get("text", "")),
            "spoken": spoken,
            "tts": tts_info,
            "provider": router_result.get("provider", "none"),
            "model": router_result.get("model", ""),
            "local_matched": local_matched,
            "openrouter_called": bool(router_result.get("openrouter_called", False)),
            "fish_audio_called": bool(router_result.get("fish_audio_called", False)),
            "error": router_result.get("error"),
            "latency": latency,
            "actions": router_result.get("actions", []),
            "requires_confirmation": bool(router_result.get("requires_confirmation", False)),
            "command_id": router_result.get("command_id", f"cmd_{uuid4().hex[:12]}"),
            "status": router_result.get("status", "completed"),
            "handled": bool(router_result.get("handled", True)),
            "executed": bool(router_result.get("executed", True))
        }

        # Log completion
        self.logger.info(
            "Assistant request completed: id=%s mode=%s intent=%s response='%s' spoken=%s latency=%sms",
            response.get("command_id"),
            response["mode"],
            response.get("route_detail"),
            response["text"][:100],
            response["spoken"],
            total_ms,
        )

        return response

    async def ask_assistant(
        self,
        text: str,
        speak: bool = True,
        source: str = "hud",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Keep for backwards compatibility, routing to the new robust ask method."""
        return await self.ask(text=text, speak=speak, source=source, context=context)
