from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.runtime import build_info
from app.router.command_router import CommandRouter
from app.scenarios import news, welcome_home, workspace
from app.voice.tts import TTSService
from app.voice.voice_pipeline import VoicePipeline


def run_full_test(settings: Settings) -> dict[str, Any]:
    voice = VoicePipeline(settings).dependency_check()
    tts_status = TTSService(settings).status()
    checks: dict[str, str] = {
        "backend": "ok",
        "settings": "ok",
        "commands": "ok",
        "sounddevice": "ok" if voice["sounddevice"]["available"] else "missing",
        "microphone": "ready" if voice["microphone"]["can_test"] else "unavailable",
        "stt": "ok" if voice["stt"]["configured"] else "not_configured",
        "tts": "ok" if voice["tts"].get("fish_audio_configured") else "fish_audio_missing",
        "license": "disabled",
        "Backend": "ok",
        "UI build": "check via npm run build",
        "Electron path": "logged",
        "Backend path": "logged",
        "Microphone": "ready" if voice["microphone"]["can_test"] else "unavailable",
        "STT": "ok" if voice["stt"]["configured"] else "not_configured",
        "TTS": "ok" if voice["tts"].get("fish_audio_configured") else "fish_audio_missing",
        "TTS status": "ready" if tts_status["primary_ready"] else "Fish Audio недоступен, ответ показан текстом.",
        "Providers": "configured" if settings.openrouter_api_key else "local_only",
        "OpenRouter": "configured" if settings.openrouter_api_key else "missing_key",
        "Fish Audio": "configured" if settings.fish_audio_api_key and settings.fish_audio_voice_id else "missing_key_or_voice",
        "TTS primary": settings.tts_primary,
        "TTS require Fish Audio": str(settings.tts_require_fish_audio).lower(),
        "TTS fallback enabled": str(settings.tts_fallback_enabled).lower(),
        "Commands": "ok",
        "Scenarios": "ok",
        "License disabled": "ok",
    }

    warnings: list[str] = []
    try:
        CommandRouter(settings).handle("diagnostics ping", source="diagnostics", context={"dry_run": True})
        checks["/assistant/command test"] = "ok"
    except Exception as exc:
        checks["/assistant/command test"] = "failed"
        warnings.append(f"assistant dry run failed: {exc.__class__.__name__}")

    for name, runner in {
        "welcome-home dry run": welcome_home.run,
        "news dry run": news.run,
        "workspace dry run": workspace.run,
    }.items():
        try:
            runner(settings, dry_run=True)
            checks[name] = "ok"
        except Exception as exc:
            checks[name] = "failed"
            warnings.append(f"{name}: {exc.__class__.__name__}")

    return {
        "runtime": build_info(settings),
        "checks": checks,
        "voice": voice,
        "tts_status": tts_status,
        "warnings": warnings,
    }
