from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.core.config import env_debug_status, get_settings, patch_settings
from app.core.logging import configure_logging, get_logger
from app.core.runtime import build_info
from app.diagnostics.dependencies import check_backend_dependencies
from app.diagnostics.full_test import run_full_test
from app.events.websocket_bus import event_bus
from app.pc.system import get_system_status
from app.router.ai_planner import AIPlanner
from app.router.command_router import CommandRouter
from app.providers.fish_audio import FishAudioTTS
from app.providers.groq import GroqPlanner
from app.providers.openrouter import OpenRouterPlanner
from app.scenarios import music, news, welcome_home, workspace
from app.storage.command_store import create_command, delete_command, get_commands, update_command
from app.voice.microphone import VoiceDependencyError
from app.voice.tts import TTSService
from app.voice.speech_orchestrator import last_tts_state
from app.voice.speech_queue import speech_queue
from app.voice.voice_pipeline import VoicePipeline, voice_error_response
from app.core.assistant_orchestrator import AssistantOrchestrator
from app.features.reminders import reminder_service
from app.voice.listener import voice_listener


configure_logging()
logger = get_logger(__name__)

from contextlib import asynccontextmanager

def safe_start_reminder_service() -> None:
    try:
        logger.info("Starting reminder service safely on app startup...")
        reminder_service.cleanup_old_reminders()
        reminder_service.start()
    except Exception as e:
        logger.exception("Failed to start reminder_service: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    safe_start_reminder_service()

    settings = get_settings()
    if settings.listener_enabled and settings.listener_autostart:
        try:
            logger.info("Listener autostart enabled. Verifying safe-start gates before starting voice listener...")
            voice_listener.device_id = settings.listener_device_id
            gate_res = voice_listener.check_safe_start(settings.listener_device_id)
            if gate_res["safe_to_start"]:
                voice_listener.start(
                    device_id=settings.listener_device_id,
                    wake_word_enabled=True,
                    clap_enabled=False,
                    force_start=True,
                )
                logger.info("Voice listener started safely on startup.")
            else:
                voice_listener.block(
                    gate_res["failed_check"] or "listener_blocked",
                    gate_res["fix"],
                    gate_res["fix"] or gate_res["failed_check"],
                )
                logger.warning(
                    "Voice listener startup blocked by safe gate. Reason: %s. Fix: %s",
                    gate_res["failed_check"],
                    gate_res["fix"]
                )
        except Exception as e:
            logger.exception("Failed to start voice_listener on startup: %s", e)
            voice_listener.block("unknown_exception", "Проверьте микрофон, STT и зависимости voice runtime.", str(e))
    else:
        logger.info("Voice listener auto-start is disabled.")

    yield

    # Shutdown:
    try:
        reminder_service.stop()
    except Exception:
        pass
    try:
        voice_listener.stop()
    except Exception:
        pass

app = FastAPI(title="JARVIS PC V2 Backend", version="0.1.0", lifespan=lifespan)
app.started_at = time.time()


@app.get("/runtime/process-info")
def runtime_process_info() -> dict[str, Any]:
    import os
    import time
    from datetime import datetime

    started_timestamp = getattr(app, "started_at", None)
    if started_timestamp is None:
        started_timestamp = time.time()
        app.started_at = started_timestamp

    started_at_str = datetime.fromtimestamp(started_timestamp).isoformat()

    return {
        "pid": os.getpid(),
        "host": os.getenv("JARVIS_BACKEND_HOST", "127.0.0.1"),
        "port": int(os.getenv("JARVIS_BACKEND_PORT", "18000")),
        "cwd": os.getcwd(),
        "started_at": started_at_str,
        "mode": "dev",
        "launcher": os.getenv("JARVIS_LAUNCHER", "START_JARVIS")
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "app://jarvis", "file://", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source: str = "manual"
    context: dict[str, Any] = Field(default_factory=dict)


class CustomCommandRequest(BaseModel):
    title: str = Field(..., min_length=1)
    phrases: list[str] = Field(default_factory=list)
    action_type: str = Field(..., min_length=1)
    action_value: str = ""
    enabled: bool = True
    confirm_required: bool | None = None


class CustomCommandPatchRequest(BaseModel):
    title: str | None = None
    phrases: list[str] | None = None
    action_type: str | None = None
    action_value: str | None = None
    enabled: bool | None = None
    confirm_required: bool | None = None


class AskRequest(BaseModel):
    text: str = Field(..., min_length=1)
    speak: bool = True
    source: str = "hud"
    context: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    text: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class SettingsPatchRequest(BaseModel):
    debug_mode: bool | None = None
    chatgpt_url: str | None = None
    news_url: str | None = None
    news_rss_url: str | None = None
    workspace_project_path: str | None = None
    open_terminal_with_workspace: bool | None = None
    ai_primary: str | None = None
    ai_fallback: str | None = None
    ai_allow_local_fallback: bool | None = None
    voice_profile: str | None = None
    assistant_name: str | None = None
    assistant_display_name: str | None = None
    assistant_address_style: str | None = None
    wake_words: list[str] | str | None = None
    voice_profile_id: str | None = None
    voice_profiles: list[dict[str, Any]] | None = None
    voice_tone: str | None = None
    voice_wake_enabled: bool | None = None
    clap_enabled: bool | None = None
    runtime_mode: str | None = None
    autostart_enabled: bool | None = None
    listener_enabled: bool | None = None
    listener_autostart: bool | None = None
    listener_device_id: str | None = None
    voice_volume: int | None = Field(default=None, ge=0, le=100)
    offline_mode: bool | None = None


class ScenarioTestRequest(BaseModel):
    scenario: str
    dry_run: bool = True


class MicrophoneTestRequest(BaseModel):
    device_id: str = "default"
    duration_seconds: float = Field(default=3, gt=0, le=30)


class TestCaptureRequest(BaseModel):
    device_id: str = "default"
    duration_seconds: float = Field(default=3, gt=0, le=30)



class RecordCommandRequest(BaseModel):
    device_id: str = "default"
    max_seconds: float = Field(default=8, gt=0, le=30)
    send_to_assistant: bool = True
    text_override: str | None = None
    dry_run: bool = False


class ListenerRequest(BaseModel):
    wake_word: bool = True
    clap: bool = False
    device_id: str = "default"


class CalibrateMicRequest(BaseModel):
    device_id: str = "default"
    silence_seconds: float = 2.0
    speech_seconds: float = 3.0


class ListenerStartRequest(BaseModel):
    device_id: str = "default"
    wake_word: bool = True
    clap: bool = False


class SayRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ProviderTextRequest(BaseModel):
    text: str | None = None


class JarvisVoiceTestRequest(BaseModel):
    text: str = "Проверка голоса Джарвиса. Я на связи, сэр."


class FullPipelineTestRequest(BaseModel):
    text: str = "Джарвис как дела?"


def envelope(data: Any, *, ok: bool = True, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": ok, "data": data, "error": error}


def command_envelope(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("tts"), dict) and "audio" in result["tts"]:
        result = dict(result)
        result["tts"] = dict(result["tts"])
        result["tts"]["audio"] = None
    ok = bool(result.get("ok", True))
    if result.get("mode") in {"ai_limited", "local", "text_only"}:
        ok = True
    return {
        **envelope(result, ok=ok, error=result.get("error") if not ok else None),
        "handled": bool(result.get("handled", True)),
        "executed": bool(result.get("executed", result.get("status") == "completed" or result.get("mode") in {"ai_limited", "local", "text_only"})),
        "route": result.get("route"),
        "provider": result.get("provider"),
        "action": result.get("action") or result.get("route"),
        "text": result.get("text") or result.get("response_text") or "Команда выполнена.",
        "openrouter_called": bool(result.get("openrouter_called", False)),
        "fish_audio_called": bool(result.get("fish_audio_called", False)),
        "local_matched": bool(result.get("local_matched", False)),
        "model": result.get("model"),
        "tts": result.get("tts"),
        "latency": result.get("latency"),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return envelope({"status": "ok", "service": "jarvis-pc-v2-backend"})


@app.get("/health/full")
def health_full() -> dict[str, Any]:
    settings = get_settings()
    return envelope(
        {
            "backend": "ok",
            "settings": "ok",
            "commands": "ok",
            "voice": "text_only",
            "ai": "configured" if settings.openrouter_api_key else "not_configured",
            "tts": "fish_audio" if settings.fish_audio_api_key and settings.fish_audio_voice_id else "not_configured",
            "warnings": [],
        }
    )


@app.get("/app/status")
def app_status() -> dict[str, Any]:
    settings = get_settings()
    return envelope(
        {
            "app_name": "JARVIS PC V2 Minimal Assistant",
            "status": "local",
            "ui": "minimal_assistant",
            "backend": "ok",
            "license": "disabled",
            "version": settings.version,
        }
    )


@app.get("/runtime/build-info")
def runtime_build_info() -> dict[str, Any]:
    return envelope(build_info(get_settings()))


@app.get("/license/status")
def license_status() -> dict[str, Any]:
    return envelope(
        {
            "enabled": False,
            "blocking": False,
            "status": "disabled",
            "message": "Лицензия отключена для локальной PC-версии.",
        }
    )


@app.get("/voice/dependency-check")
def voice_dependency_check() -> dict[str, Any]:
    return envelope(VoicePipeline(get_settings()).dependency_check())


@app.get("/voice/tts-status")
def voice_tts_status() -> dict[str, Any]:
    data = TTSService(get_settings()).status()
    data.update(speech_queue.status())
    return envelope(data)


@app.post("/voice/tts-reset")
def voice_tts_reset() -> dict[str, Any]:
    return envelope(speech_queue.reset())


@app.get("/debug/voice-provider-status")
def debug_voice_provider_status() -> dict[str, Any]:
    settings = get_settings()
    env_status = env_debug_status(settings)
    require_fish = bool(settings.tts_require_fish_audio or settings.selected_voice_provider() == "fish_audio" or settings.voice_profile.strip().lower() == "jarvis style")
    fish_key_present = bool(settings.fish_audio_api_key)
    fish_voice_present = bool(settings.fish_audio_voice_id)
    selected_provider = "fish_audio" if fish_key_present and fish_voice_present else "text_only"

    fixes: list[str] = []
    if not fish_key_present or not fish_voice_present:
        fixes.append("Добавьте JARVIS_FISH_AUDIO_API_KEY и JARVIS_FISH_AUDIO_VOICE_ID в backend/.env")

    last_state = last_tts_state()
    queue_state = speech_queue.status()
    return envelope(
        {
            "env_loaded": bool(env_status.get("env_loaded")),
            "paths_loaded": env_status.get("paths_loaded") or env_status.get("env_paths_loaded") or [],
            "voice_profile": settings.voice_profile,
            "voice_profile_id": settings.voice_profile_id,
            "voice_tone": settings.effective_voice_tone(),
            "tts_primary": "fish_audio" if require_fish else settings.tts_primary,
            "require_fish_audio": require_fish,
            "fallback_enabled": bool(settings.tts_fallback_enabled and not require_fish),
            "fish_key_present": fish_key_present,
            "fish_voice_id_present": fish_voice_present,
            "selected_provider": selected_provider,
            "queue_size": queue_state["queue_size"],
            "active_job_id": queue_state["active_job_id"],
            "last_job_id": queue_state["last_job_id"],
            "last_job_status": queue_state["last_job_status"] or "none",
            "last_job_age_seconds": queue_state.get("last_job_age_seconds", 0),
            "last_provider": last_state["last_provider"],
            "last_error_type": last_state["last_error_type"],
            "last_error": last_state["last_error"],
            "fixes": fixes,
        }
    )


@app.get("/debug/local-voice-status")
def debug_local_voice_status() -> dict[str, Any]:
    from app.voice.local_providers import GPTSoVITSLocalProvider, PiperLocalProvider, RVCConverterProvider, XTTSLocalProvider

    settings = get_settings()
    fish_key_present = bool(settings.fish_audio_api_key)
    fish_voice_present = bool(settings.fish_audio_voice_id)
    return envelope(
        {
            "fish_audio": {
                "enabled": settings.tts_primary == "fish_audio" or settings.voice_provider == "fish_audio",
                "key_present": fish_key_present,
                "voice_id_present": fish_voice_present,
                "available": fish_key_present and fish_voice_present,
            },
            "piper_local": PiperLocalProvider(settings).status().to_dict(),
            "xtts_local": XTTSLocalProvider(settings).status().to_dict(),
            "gpt_sovits_local": GPTSoVITSLocalProvider(settings).status().to_dict(),
            "rvc_converter": RVCConverterProvider(settings).status().to_dict(),
            "text_only": {"enabled": True, "available": True, "install_hint": None},
        }
    )


@app.get("/voice/offline-voices")
def voice_offline_voices() -> dict[str, Any]:
    try:
        import pyttsx3
        import pythoncom
        pythoncom.CoInitialize()
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            res = []
            for v in voices:
                res.append({
                    "id": v.id,
                    "name": v.name,
                    "languages": getattr(v, "languages", []),
                    "gender": getattr(v, "gender", None)
                })
            return envelope(res)
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        return envelope([], ok=False, error={"code": "OFFLINE_VOICES_ERROR", "message": str(e)})


@app.post("/voice/say")
def voice_say(request: SayRequest) -> dict[str, Any]:
    result = TTSService(get_settings()).speak(request.text, blocking=True)
    provider = result.get("provider") or "text_only"
    if provider == "none":
        provider = "text_only"
    summary = {
        "ok": bool(result.get("ok", False)),
        "provider": provider,
        "spoken": bool(result.get("spoken", False)),
        "played": bool(result.get("played", False)),
        "fallback_used": bool(result.get("fallback_used", False)),
        "error": result.get("error"),
        "error_type": result.get("error_type"),
        "fix": result.get("fix") or "Проверьте настройки голоса в .env.",
    }
    return {
        **summary,
        "data": summary,
        "error": {"code": "TTS_ERROR", "message": str(result.get("error")), "details": {"fix": result.get("fix")}} if not result.get("ok", False) else None,
    }


@app.get("/debug/dependencies")
def debug_dependencies() -> dict[str, Any]:
    return check_backend_dependencies()


@app.get("/debug/network-status")
def debug_network_status() -> dict[str, Any]:
    import socket
    import time
    import httpx
    import requests
    from app.providers.openrouter import _fix_for, classify_openrouter_exception

    dns_ok = False
    tcp_ok = False
    httpx_ok = False
    requests_ok = False
    status_code = None
    error_type = None
    fix = None
    errors: dict[str, str | None] = {"dns": None, "tcp": None, "httpx": None, "requests": None}
    started = time.perf_counter()

    try:
        socket.getaddrinfo("openrouter.ai", 443)
        dns_ok = True
    except Exception as e:
        errors["dns"] = str(e)
        error_type = "network_timeout"

    if dns_ok:
        try:
            with socket.create_connection(("openrouter.ai", 443), timeout=10):
                tcp_ok = True
        except Exception as e:
            errors["tcp"] = str(e)
            error_type = classify_openrouter_exception(e)

    if tcp_ok:
        try:
            timeout = httpx.Timeout(30.0, connect=10.0, read=20.0)
            with httpx.Client(timeout=timeout, trust_env=True) as client:
                response = client.get("https://openrouter.ai/api/v1/models")
            status_code = response.status_code
            httpx_ok = response.status_code == 200
            if httpx_ok:
                error_type = None
            else:
                error_type = "provider_error"
                errors["httpx"] = f"HTTP {response.status_code}: {response.text[:200]}"
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as e:
            errors["httpx"] = str(e) or e.__class__.__name__
            error_type = classify_openrouter_exception(e)
        except Exception as e:
            errors["httpx"] = str(e) or e.__class__.__name__
            error_type = classify_openrouter_exception(e)

    if not httpx_ok and dns_ok:
        try:
            response = requests.get(
                "https://openrouter.ai/api/v1/models",
                timeout=(10, 20),
            )
            status_code = response.status_code
            requests_ok = response.status_code == 200
            if requests_ok:
                error_type = None
            else:
                error_type = "provider_error"
                errors["requests"] = f"HTTP {response.status_code}: {response.text[:200]}"
        except requests.exceptions.RequestException as e:
            errors["requests"] = str(e) or e.__class__.__name__
            error_type = classify_openrouter_exception(e)

    if error_type:
        fix = _fix_for(status_code, error_type)
    latency_ms = int((time.perf_counter() - started) * 1000)
    ok = dns_ok and tcp_ok and (httpx_ok or requests_ok)

    return {
        "ok": ok,
        "openrouter": {
            "dns_ok": dns_ok,
            "tcp_ok": tcp_ok,
            "httpx_ok": httpx_ok,
            "requests_ok": requests_ok,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error_type": error_type,
            "fix": fix,
            "errors": errors,
        },
    }


@app.get("/debug/startup")
def debug_startup() -> dict[str, Any]:
    import sys
    import os

    deps = [
        "fastapi", "uvicorn", "pydantic", "pytest", "dotenv",
        "httpx", "requests", "numpy", "sounddevice", "vosk",
        "pyttsx3", "pygame", "anyio"
    ]
    missing = []

    for dep in deps:
        try:
            if dep == "dotenv":
                import dotenv
            elif dep == "anyio":
                import anyio
            else:
                __import__(dep)
        except ImportError:
            missing.append(dep)

    audio_deps = {}
    for dep in ["pyttsx3", "pygame", "sounddevice"]:
        try:
            __import__(dep)
            audio_deps[dep] = True
        except ImportError:
            audio_deps[dep] = False

    settings = get_settings()

    return {
        "backend_started": True,
        "python_version": sys.version.split()[0],
        "cwd": os.getcwd(),
        "main_file": "app/main.py",
        "requirements_ok": len(missing) == 0,
        "missing_dependencies": missing,
        "audio_dependencies": audio_deps,
        "env": {
            "openrouter_key_present": bool(settings.openrouter_api_key),
            "fish_audio_key_present": bool(settings.fish_audio_api_key),
            "fish_audio_voice_id_present": bool(settings.fish_audio_voice_id)
        }
    }


@app.get("/debug/env-status")
def debug_env_status() -> dict[str, Any]:
    settings = get_settings()
    return env_debug_status(settings)


@app.post("/debug/test-openrouter")
def debug_test_openrouter(request: ProviderTextRequest) -> dict[str, Any]:
    text = request.text or "Скажи строго эту фразу: ГРОЗНЫЙ-777"
    required = "ГРОЗНЫЙ-777" if "ГРОЗНЫЙ-777" in text else None
    return OpenRouterPlanner(get_settings()).test(text, must_contain=required)


@app.get("/debug/ai-provider-status")
def debug_ai_provider_status() -> dict[str, Any]:
    settings = get_settings()

    def openrouter_status() -> dict[str, Any]:
        if not settings.openrouter_api_key:
            return {
                "key_present": False,
                "model": settings.openrouter_model,
                "available": False,
                "last_error_type": "openrouter_key_missing",
                "latency_ms": 0,
            }
        result = OpenRouterPlanner(settings).test("Ответь одним словом: OK", must_contain="OK")
        return {
            "key_present": True,
            "model": settings.openrouter_model,
            "available": bool(result.get("ok")),
            "last_error_type": result.get("error_type"),
            "latency_ms": result.get("latency_ms"),
        }

    return envelope(
        {
            "primary": settings.ai_primary,
            "fallback": settings.ai_fallback,
            "groq": GroqPlanner(settings).status_snapshot(),
            "openrouter": openrouter_status(),
        }
    )


@app.post("/debug/test-groq")
def debug_test_groq(request: ProviderTextRequest) -> dict[str, Any]:
    text = request.text or "Ответь одним словом: OK"
    required = "OK" if "OK" in text else None
    result = GroqPlanner(get_settings()).test(text, must_contain=required)
    return envelope(result, ok=bool(result.get("ok")))


@app.post("/debug/test-ai-brain")
async def debug_test_ai_brain() -> dict[str, Any]:
    settings = get_settings()
    steps = []
    fixes = []

    # 1. Environment Status Step
    started_env = time.perf_counter()
    env_status = env_debug_status(settings)
    env_fixes = env_status.get("fixes", [])
    fixes.extend(env_fixes)
    steps.append({
        "name": "env_check",
        "ok": len(env_fixes) == 0,
        "message": "Environment settings checked." if len(env_fixes) == 0 else "Missing environment settings.",
        "details": env_status,
        "latency_ms": int((time.perf_counter() - started_env) * 1000)
    })

    # 2. OpenRouter Test Step
    started_or = time.perf_counter()
    if settings.openrouter_api_key:
        try:
            or_test = OpenRouterPlanner(settings).test("Скажи строго эту фразу: ГРОЗНЫЙ-777", must_contain="ГРОЗНЫЙ-777")
            or_ok = bool(or_test.get("ok"))
            or_msg = "OpenRouter connection test passed." if or_ok else f"OpenRouter connection test failed: {or_test.get('error_message')}"
            if or_test.get("fix"):
                fixes.append(or_test["fix"])
        except Exception as e:
            or_test = {"ok": False, "error_message": str(e), "error_type": "exception"}
            or_ok = False
            or_msg = f"OpenRouter exception during test: {str(e)}"
            fixes.append("Проверьте интернет-соединение или настройки прокси.")
    else:
        or_test = {"ok": False, "error_type": "key_missing", "error_message": "OpenRouter API key is missing."}
        or_ok = False
        or_msg = "OpenRouter test skipped: API key is missing."

    steps.append({
        "name": "openrouter_test",
        "ok": or_ok,
        "message": or_msg,
        "details": or_test,
        "latency_ms": int((time.perf_counter() - started_or) * 1000)
    })

    # 3. Assistant Routing Step
    started_ask = time.perf_counter()
    orchestrator = AssistantOrchestrator(settings)
    try:
        ask_res = await orchestrator.ask(
            text="Как тебя зовут?",
            speak=True,
            source="diagnostic",
            context={"dry_run": True}
        )
        ask_ok = bool(ask_res.get("ok"))
        ask_msg = "Assistant ask query completed." if ask_ok else f"Assistant ask query failed: {ask_res.get('text')}"
        if ask_res.get("error") and isinstance(ask_res["error"], dict) and ask_res["error"].get("fix"):
            fixes.append(ask_res["error"]["fix"])
    except Exception as e:
        ask_res = {"ok": False, "error": str(e)}
        ask_ok = False
        ask_msg = f"Assistant ask query raised exception: {str(e)}"
        fixes.append("Check assistant orchestrator logs for crashes.")

    steps.append({
        "name": "assistant_ask",
        "ok": ask_ok,
        "message": ask_msg,
        "details": ask_res,
        "latency_ms": int((time.perf_counter() - started_ask) * 1000)
    })

    # 4. TTS Step
    started_tts = time.perf_counter()
    try:
        tts = TTSService(settings)
        tts_res = tts.speak("Тест.", dry_run=True)
        tts_ok = bool(tts_res.get("ok"))
        tts_msg = "TTS synthesis test passed." if tts_ok else f"TTS synthesis test failed: {tts_res.get('error')}"
        if tts_res.get("fix"):
            fixes.append(tts_res["fix"])
    except Exception as e:
        tts_res = {"ok": False, "error": str(e)}
        tts_ok = False
        tts_msg = f"TTS test raised exception: {str(e)}"
        fixes.append("Check TTS service settings.")

    steps.append({
        "name": "tts_test",
        "ok": tts_ok,
        "message": tts_msg,
        "details": tts_res,
        "latency_ms": int((time.perf_counter() - started_tts) * 1000)
    })

    # Deduplicate fixes keeping original order
    seen_fixes = set()
    deduped_fixes = []
    for f in fixes:
        if f and f not in seen_fixes:
            seen_fixes.add(f)
            deduped_fixes.append(f)

    final_ok = all(s["ok"] for s in steps)

    return {
        "ok": final_ok,
        "steps": steps,
        "final_text": ask_res.get("text") if isinstance(ask_res, dict) else None,
        "spoken": ask_res.get("spoken") if isinstance(ask_res, dict) else False,
        "fixes": deduped_fixes
    }


@app.post("/debug/test-fish-audio")
def debug_test_fish_audio(request: ProviderTextRequest) -> dict[str, Any]:
    settings = get_settings()
    started = time.perf_counter()
    text = request.text or "Проверка голоса Джарвиса. Код семь семь семь."
    result = TTSService(settings).speak(text)
    latency_ms = result.get("latency_ms")
    if latency_ms is None:
        latency_ms = int((time.perf_counter() - started) * 1000)
    if result.get("ok"):
        return {
            "ok": True,
            "provider": result.get("provider", "fish_audio"),
            "voice_id_present": bool(settings.fish_audio_voice_id),
            "voice_id": "masked" if settings.fish_audio_voice_id else None,
            "status_code": result.get("status_code"),
            "audio_bytes": result.get("audio_bytes"),
            "played": bool(result.get("played")),
            "fallback_used": bool(result.get("fallback_used", False)),
            "format": result.get("format"),
            "latency_ms": latency_ms,
        }
    return {
        "ok": False,
        "provider": result.get("provider", "fish_audio"),
        "voice_id_present": bool(settings.fish_audio_voice_id),
        "voice_id": "masked" if settings.fish_audio_voice_id else None,
        "status_code": result.get("status_code"),
        "error_type": result.get("status"),
        "error_message": result.get("error"),
        "fix": result.get("fix"),
        "fallback_used": bool(result.get("fallback_used", False)),
        "audio_bytes": result.get("audio_bytes") or 0,
        "played": bool(result.get("played")),
        "latency_ms": latency_ms,
    }


@app.post("/debug/test-jarvis-voice")
def debug_test_jarvis_voice(request: JarvisVoiceTestRequest) -> dict[str, Any]:
    settings = get_settings()
    text = request.text or "Проверка голоса Джарвиса. Я на связи, сэр."
    result = TTSService(settings).speak(text, blocking=True)
    provider = result.get("provider") or "text_only"
    if provider == "none":
        provider = "text_only"
    job_status = "played" if result.get("played") else "failed"
    data = {
        "ok": bool(result.get("ok")),
        "provider": provider,
        "job_status": job_status,
        "error_type": result.get("error_type"),
        "error": result.get("error") or result.get("error_message"),
        "fix": result.get("fix") or "Добавьте JARVIS_FISH_AUDIO_API_KEY и JARVIS_FISH_AUDIO_VOICE_ID в backend/.env",
        "played": bool(result.get("played")),
        "audio_bytes": result.get("audio_bytes") or 0,
        "latency_ms": result.get("latency_ms") or 0,
    }
    return envelope(
        data,
        ok=bool(result.get("ok")),
        error=None if result.get("ok") else {"code": "TTS_ERROR", "message": str(result.get("error")), "details": data},
    )


@app.post("/debug/test-full-pipeline")
def debug_test_full_pipeline(request: FullPipelineTestRequest) -> dict[str, Any]:
    return CommandRouter(get_settings()).handle(
        request.text,
        source="debug_full_pipeline",
        context={"tts_wait": True},
    )


@app.get("/voice/devices")
def voice_devices() -> dict[str, Any]:
    try:
        return envelope(VoicePipeline(get_settings()).devices())
    except VoiceDependencyError as exc:
        return envelope(None, ok=False, error=voice_error_response(exc))


@app.get("/voice/mic-diagnostics")
def voice_mic_diagnostics() -> dict[str, Any]:
    from app.voice.microphone import mic_diagnostics
    diagnostics = mic_diagnostics()
    default_dev = diagnostics.get("default_input_device")
    selected_id = default_dev.get("id") if default_dev else "default"

    data = {
        "sounddevice_available": diagnostics.get("sounddevice_available"),
        "numpy_available": diagnostics.get("numpy_available"),
        "default_input_device": default_dev,
        "input_devices": diagnostics.get("input_devices"),
        "selected_device_id": selected_id,
        "can_record": diagnostics.get("can_record"),
        "windows_hint": diagnostics.get("windows_hint"),
        "windows_microphone_hint": diagnostics.get("windows_hint"),
        "fixes": diagnostics.get("fixes")
    }
    return envelope(data)


@app.post("/voice/test-capture")
def voice_test_capture(request: TestCaptureRequest) -> dict[str, Any]:
    from app.voice.microphone import capture_audio, resolve_input_device, VoiceDependencyError

    # Resolve device to get clean name
    dev_res = resolve_input_device(request.device_id)
    device_name = dev_res.get("device_name", "Unknown Device")

    try:
        capture = capture_audio(
            device_id=request.device_id,
            duration_seconds=request.duration_seconds,
        )
        rms = capture.rms
        peak = capture.peak
        heard = rms > 0.005 or peak > 0.02

        fix_msg = None
        error_type = None
        if not heard:
            error_type = "no_audio"
            fix_msg = "Проверьте разрешение Windows для микрофона, уровень громкости и выбранное устройство."

        data = {
            "ok": heard,
            "device_id": str(request.device_id),
            "device_name": device_name,
            "sample_rate": capture.sample_rate,
            "channels": capture.channels,
            "duration_seconds": request.duration_seconds,
            "rms": rms,
            "peak": peak,
            "heard_signal": heard,
            "error_type": error_type,
            "fix": fix_msg
        }

        err_envelope = None
        if not heard:
            err_envelope = {
                "code": "NO_AUDIO_HEARD",
                "message": "Микрофон не получает звук.",
                "error_type": "no_audio",
                "fix": fix_msg
            }

        return envelope(data, ok=heard, error=err_envelope)

    except Exception as exc:
        error_code = getattr(exc, "code", "CAPTURE_FAILED")
        fix_msg = "Проверьте разрешение Windows для микрофона, уровень громкости и выбранное устройство."
        if isinstance(exc, VoiceDependencyError) and exc.details.get("install_hint"):
            fix_msg = f"Установите зависимости: {exc.details['install_hint']}"

        data = {
            "ok": False,
            "device_id": str(request.device_id),
            "device_name": device_name,
            "sample_rate": 16000,
            "channels": 1,
            "duration_seconds": request.duration_seconds,
            "rms": 0.0,
            "peak": 0.0,
            "heard_signal": False,
            "error_type": error_code,
            "fix": fix_msg
        }
        return envelope(data, ok=False, error={"code": "CAPTURE_FAILED", "message": str(exc), "details": {"fix": fix_msg}})


@app.get("/voice/stt-status")
def voice_stt_status() -> dict[str, Any]:
    from app.voice.stt import stt_status
    return envelope(stt_status(get_settings()))


@app.post("/voice/test-microphone")
def voice_test_microphone(request: MicrophoneTestRequest) -> dict[str, Any]:
    event_bus.emit("voice.microphone.test.started", {"device_id": request.device_id})
    try:
        result = VoicePipeline(get_settings()).test_microphone(
            device_id=request.device_id,
            duration_seconds=request.duration_seconds,
        )
    except VoiceDependencyError as exc:
        event_bus.emit("voice.error", {"code": exc.code})
        return envelope(None, ok=False, error=voice_error_response(exc))

    event_bus.emit("voice.microphone.test.completed", {"device_id": request.device_id, "rms": result["rms"]})
    return envelope(result)


@app.post("/voice/record-command")
def voice_record_command(request: RecordCommandRequest) -> dict[str, Any]:
    import traceback
    event_bus.emit("voice.recording.started", {"device_id": request.device_id})
    try:
        result = VoicePipeline(get_settings()).record_command(
            device_id=request.device_id,
            max_seconds=request.max_seconds,
            send_to_assistant=request.send_to_assistant,
            text_override=request.text_override,
            dry_run=request.dry_run,
        )
        transcript = result.get("stt", {}).get("transcript") if isinstance(result.get("stt"), dict) else result.get("transcript")
        event_bus.emit(
            "voice.recording.completed",
            {"device_id": request.device_id, "transcript_available": bool(transcript)},
        )

        if not result.get("ok", True):
            error_payload = {
                "code": "VOICE_RECORD_ERROR",
                "message": result.get("stt", {}).get("fix") or "Voice recording failed",
                "error_type": result.get("stt", {}).get("error_type") or "CAPTURE_FAILED",
                "fix": result.get("stt", {}).get("fix") or "Проверьте выбранный микрофон."
            }
            return envelope(result, ok=False, error=error_payload)

        return envelope(result, ok=result.get("ok", True))
    except Exception as exc:
        logger.exception("Exception inside voice_record_command endpoint")
        error_msg = str(exc)
        error_type = exc.__class__.__name__
        fix_msg = "Проверьте выбранный микрофон, доступ Windows к микрофону, уровень громкости, разрешение для desktop apps."
        if isinstance(exc, VoiceDependencyError) and exc.details.get("install_hint"):
            fix_msg = f"Установите зависимости: {exc.details['install_hint']}"

        error_payload = {
            "code": "VOICE_RECORD_ERROR",
            "message": error_msg,
            "error_type": error_type,
            "fix": fix_msg
        }

        fallback_data = {
            "final_status": "record_error",
            "capture": None,
            "stt": None,
            "assistant_result": None
        }

        event_bus.emit("voice.error", {"code": "VOICE_RECORD_ERROR", "message": error_msg})
        return envelope(fallback_data, ok=False, error=error_payload)


def make_listener_response(ok: bool, error_dict: dict[str, Any] | None = None) -> dict[str, Any]:
    status_dict = voice_listener.status()
    settings = get_settings()
    reason = status_dict["data"].get("reason")
    if not settings.listener_enabled and not reason:
        reason = "listener disabled by default"
        status_dict["data"]["reason"] = reason

    return {
        "ok": ok,
        "data": status_dict["data"],
        "error": error_dict
    }


@app.get("/voice/listener-status")
def voice_listener_status() -> dict[str, Any]:
    status_data = voice_listener.status()
    return make_listener_response(status_data["ok"])


@app.post("/voice/listener-start")
def voice_listener_start_post(request: ListenerStartRequest) -> dict[str, Any]:
    patch_settings(
        {
            "listener_enabled": True,
            "listener_autostart": True,
            "listener_device_id": request.device_id,
            "voice_wake_enabled": request.wake_word,
            "clap_enabled": False,
        }
    )
    voice_listener.device_id = request.device_id
    gate_res = voice_listener.check_safe_start(request.device_id)
    if not gate_res["safe_to_start"]:
        error_payload = {
            "code": "SAFE_GATE_BLOCKED",
            "message": gate_res["fix"] or f"Blocked by check: {gate_res['failed_check']}",
            "details": {
                "failed_check": gate_res["failed_check"],
                "fix": gate_res["fix"],
                "checks": gate_res["checks"]
            }
        }
        voice_listener.block(
            gate_res["failed_check"] or "listener_blocked",
            gate_res["fix"],
            gate_res["fix"] or f"Blocked by check: {gate_res['failed_check']}",
        )
        return make_listener_response(False, error_payload)

    result = voice_listener.start(
        device_id=request.device_id,
        wake_word_enabled=request.wake_word,
        clap_enabled=False,
        force_start=True
    )
    return make_listener_response(result.get("ok", True))


@app.post("/voice/listener-stop")
def voice_listener_stop_post() -> dict[str, Any]:
    result = voice_listener.stop()
    patch_settings({"listener_enabled": False, "listener_autostart": False})
    return make_listener_response(result.get("ok", True))


@app.post("/voice/calibrate-mic")
def voice_calibrate_mic(request: CalibrateMicRequest) -> dict[str, Any]:
    from app.voice.microphone import capture_audio, resolve_input_device

    dev_res = resolve_input_device(request.device_id)
    device_name = dev_res.get("device_name", "Unknown Device")

    if not dev_res["ok"]:
        data = {
            "device_id": str(request.device_id),
            "device_name": device_name,
            "noise_floor_rms": 0.0,
            "speech_rms": 0.0,
            "speech_peak": 0.0,
            "heard_signal": False,
            "recommended_min_rms_threshold": 0.003,
            "fixes": [dev_res.get("fix", "Selected device not found.")]
        }
        return envelope(data, ok=False, error={"code": "MIC_DEVICE_NOT_FOUND", "message": data["fixes"][0], "details": data})

    try:
        silence_capture = capture_audio(
            device_id=request.device_id,
            duration_seconds=request.silence_seconds,
            sample_rate=16000,
            channels=1
        )
        noise_floor_rms = silence_capture.rms

        speech_capture = capture_audio(
            device_id=request.device_id,
            duration_seconds=request.speech_seconds,
            sample_rate=16000,
            channels=1
        )
        speech_rms = speech_capture.rms
        speech_peak = speech_capture.peak

        heard_signal = speech_rms > 0.005 or speech_peak > 0.02
        recommended = max(0.003, noise_floor_rms * 1.5)

        fixes = []
        if not heard_signal:
            fixes.append("Увеличьте чувствительность микрофона в настройках Windows или выберите другое устройство.")

        data = {
            "device_id": str(request.device_id),
            "device_name": device_name,
            "noise_floor_rms": noise_floor_rms,
            "speech_rms": speech_rms,
            "speech_peak": speech_peak,
            "heard_signal": heard_signal,
            "recommended_min_rms_threshold": recommended,
            "fixes": fixes
        }
        return envelope(data, ok=heard_signal, error=None if heard_signal else {"code": "MICROPHONE_NO_AUDIO", "message": "Микрофон выбран, но сигнал не слышен.", "details": data})
    except Exception as exc:
        data = {
            "device_id": str(request.device_id),
            "device_name": device_name,
            "noise_floor_rms": 0.0,
            "speech_rms": 0.0,
            "speech_peak": 0.0,
            "heard_signal": False,
            "recommended_min_rms_threshold": 0.003,
            "fixes": [f"Ошибка калибровки: {exc}"]
        }
        return envelope(data, ok=False, error={"code": "MIC_CALIBRATION_FAILED", "message": str(exc), "details": data})


@app.post("/voice/start-listener")
def voice_start_listener(request: ListenerStartRequest) -> dict[str, Any]:
    return voice_listener_start_post(request)


@app.post("/voice/stop-listener")
def voice_stop_listener() -> dict[str, Any]:
    result = voice_listener.stop()
    patch_settings({"listener_enabled": False, "listener_autostart": False})
    event_bus.emit("voice.listener.stopped", result.get("data", {}))
    return make_listener_response(result.get("ok", True))


@app.post("/assistant/ask")
async def assistant_ask(request: AskRequest) -> dict[str, Any]:
    orchestrator = AssistantOrchestrator(get_settings())
    result = await orchestrator.ask(
        text=request.text,
        speak=request.speak,
        source=request.source,
        context=request.context,
    )
    return command_envelope(result)


@app.post("/assistant/command")
async def assistant_command(request: CommandRequest) -> dict[str, Any]:
    orchestrator = AssistantOrchestrator(get_settings())
    result = await orchestrator.ask(
        text=request.text,
        speak=True,
        source=request.source,
        context=request.context,
    )
    return command_envelope(result)


@app.post("/assistant/plan")
def assistant_plan(request: PlanRequest) -> dict[str, Any]:
    planner = AIPlanner(get_settings())
    return envelope(planner.plan(request.text).to_dict())


@app.get("/setup/readiness")
def setup_readiness() -> dict[str, Any]:
    settings = get_settings()
    warnings: list[str] = []

    # 1. Check AI configuration
    openrouter_configured = bool(settings.openrouter_api_key)
    if not openrouter_configured:
        warnings.append("OpenRouter API key is missing. AI responses will operate in limited fallback mode.")

    # 2. Check Fish Audio configuration
    fish_audio_configured = bool(settings.fish_audio_api_key)
    if not fish_audio_configured and settings.tts_primary == "fish_audio":
        warnings.append("Fish Audio API key is missing. Primary TTS is set to fish_audio but will fall back to secondary TTS.")

    # 3. Check offline TTS fallback readiness
    tts_fallback_ready = False
    try:
        from app.providers.offline_tts import OfflineTTS
        offline = OfflineTTS(settings)
        tts_fallback_ready = offline.available()
    except Exception as e:
        warnings.append(f"Offline TTS fallback check failed: {e}")

    # 4. Check microphone dependency
    microphone_dependency_ok = True
    try:
        import pyaudio
    except ImportError:
        microphone_dependency_ok = False
        warnings.append("PyAudio dependency is not installed. Live microphone listening is unavailable.")

    # 5. Check voice pipeline
    voice_pipeline_ok = True
    try:
        from app.voice.voice_pipeline import VoicePipeline
        pipe = VoicePipeline(settings)
        # Verify it can be instantiated
    except Exception as e:
        voice_pipeline_ok = False
        warnings.append(f"Voice pipeline failed to initialize: {e}")

    # 6. Check local commands
    local_commands_ok = True
    try:
        from app.storage.command_store import get_commands
        cmds = get_commands()
        if not cmds or not cmds.get("commands"):
            local_commands_ok = False
            warnings.append("Local commands list is empty or invalid.")
    except Exception as e:
        local_commands_ok = False
        warnings.append(f"Failed to load local commands: {e}")

    return envelope({
        "backend_ok": True,
        "assistant_ask_ok": True,
        "local_commands_ok": local_commands_ok,
        "openrouter_configured": openrouter_configured,
        "openrouter_model": settings.openrouter_model or "openai/gpt-4o-mini",
        "fish_audio_configured": fish_audio_configured,
        "tts_primary": settings.tts_primary or "fish_audio",
        "tts_fallback_enabled": settings.tts_fallback_enabled,
        "tts_fallback_ready": tts_fallback_ready,
        "microphone_dependency_ok": microphone_dependency_ok,
        "voice_pipeline_ok": voice_pipeline_ok,
        "hud_events_ok": True,
        "warnings": warnings
    })


@app.get("/commands/test")
def commands_test(text: str) -> dict[str, Any]:
    from app.router.intent_detector import normalize_text
    from app.storage.command_store import get_commands

    normalized = normalize_text(text)
    matched = None
    for command in get_commands().get("commands", []):
        phrases = command.get("phrases") or command.get("triggers") or []
        normalized_phrases = {normalize_text(str(phrase)) for phrase in phrases}
        if normalized in normalized_phrases or any(phrase and phrase in normalized for phrase in normalized_phrases):
            matched = command
            break

    return envelope({
        "input": text,
        "normalized": normalized,
        "matched": matched,
        "diagnostic": True,
    })


@app.post("/scenarios/welcome-home")
def scenario_welcome_home(request: ScenarioRequest) -> dict[str, Any]:
    result = welcome_home.run(get_settings(), dry_run=bool(request.context.get("dry_run", False)))
    return envelope(result)


@app.post("/scenarios/news")
def scenario_news(request: ScenarioRequest) -> dict[str, Any]:
    result = news.run(get_settings(), dry_run=bool(request.context.get("dry_run", False)))
    return envelope(result)


@app.post("/news/open-and-read")
def news_open_and_read(request: ScenarioRequest) -> dict[str, Any]:
    result = news.run(get_settings(), dry_run=bool(request.context.get("dry_run", False)))
    return envelope(result)


@app.post("/scenarios/workspace")
def scenario_workspace(request: ScenarioRequest) -> dict[str, Any]:
    result = workspace.run(get_settings(), dry_run=bool(request.context.get("dry_run", False)))
    return envelope(result)


@app.post("/scenarios/music")
def scenario_music(request: ScenarioRequest) -> dict[str, Any]:
    query = str(request.context.get("query", "Back in Black"))
    result = music.run(get_settings(), dry_run=bool(request.context.get("dry_run", False)), query=query)
    return envelope(result)


@app.get("/settings")
def settings() -> dict[str, Any]:
    return envelope(get_settings().sanitized())


@app.patch("/settings")
def settings_patch(request: SettingsPatchRequest) -> dict[str, Any]:
    patch = request.model_dump(exclude_none=True)
    updated = patch_settings(patch)
    return envelope(updated.sanitized())


@app.get("/commands")
def commands() -> dict[str, Any]:
    return envelope(get_commands())


@app.post("/commands")
def commands_create(request: CustomCommandRequest) -> dict[str, Any]:
    command = create_command(request.model_dump(exclude_none=True))
    return envelope(command)


@app.patch("/commands/{command_id}")
def commands_update(command_id: str, request: CustomCommandPatchRequest) -> dict[str, Any]:
    updated = update_command(command_id, request.model_dump(exclude_none=True))
    if not updated:
        return envelope(None, ok=False, error={"code": "COMMAND_NOT_FOUND", "message": "Command not found.", "details": {"command_id": command_id}})
    return envelope(updated)


@app.delete("/commands/{command_id}")
def commands_delete(command_id: str) -> dict[str, Any]:
    deleted = delete_command(command_id)
    if not deleted:
        return envelope(None, ok=False, error={"code": "COMMAND_NOT_FOUND", "message": "Command not found.", "details": {"command_id": command_id}})
    return envelope({"deleted": True, "command_id": command_id})


@app.get("/diagnostics/full-test")
def diagnostics_full_test() -> dict[str, Any]:
    return envelope(run_full_test(get_settings()))


@app.post("/diagnostics/full-test")
def diagnostics_full_test_post() -> dict[str, Any]:
    return envelope(run_full_test(get_settings()))


@app.get("/diagnostics/system-monitor")
def diagnostics_system_monitor() -> dict[str, Any]:
    return envelope(get_system_status())


@app.post("/diagnostics/scenario-test")
def diagnostics_scenario_test(request: ScenarioTestRequest) -> dict[str, Any]:
    settings = get_settings()
    if request.scenario == "welcome_home":
        return envelope(welcome_home.run(settings, dry_run=request.dry_run))
    if request.scenario == "news":
        return envelope(news.run(settings, dry_run=request.dry_run))
    if request.scenario == "workspace":
        return envelope(workspace.run(settings, dry_run=request.dry_run))
    if request.scenario == "music":
        return envelope(music.run(settings, dry_run=request.dry_run))
    return envelope(
        None,
        ok=False,
        error={"code": "UNKNOWN_SCENARIO", "message": "Сценарий не найден.", "details": {"scenario": request.scenario}},
    )


@app.get("/reminders")
def get_reminders_endpoint() -> dict[str, Any]:
    return envelope(reminder_service.load_reminders())


@app.post("/reminders/clear-fired")
def clear_fired_reminders_endpoint() -> dict[str, Any]:
    reminders = reminder_service.load_reminders()
    unfired = [r for r in reminders if not r.get("fired", False)]
    reminder_service.save_reminders(unfired)
    return envelope({"status": "cleared_fired", "count": len(reminders) - len(unfired)})


@app.post("/reminders/clear-all")
def clear_all_reminders_endpoint() -> dict[str, Any]:
    reminder_service.save_reminders([])
    return envelope({"status": "cleared_all"})


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await websocket.accept()
    offset = 0
    snapshot = event_bus.recent()
    offset = len(snapshot)
    await websocket.send_json({"type": "events.snapshot", "payload": snapshot})
    try:
        while True:
            offset, events = event_bus.recent_since(offset)
            for event in events:
                await websocket.send_json(event)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
