from __future__ import annotations

import json
import logging
import time
from typing import Any
import httpx

from app.core.config import Settings
from app.providers.openrouter import PlannerResult

# Standard JARVIS system prompt style
SYSTEM_PROMPT = (
    "Ты — JARVIS, русскоязычный персональный AI-ассистент на Windows PC.\n"
    "Отвечай естественно, кратко, уверенно и полезно.\n"
    "Твой стиль: спокойный, умный, немного кинематографичный, но без пафоса.\n"
    "Можно обращаться к пользователю \"сэр\", если это звучит уместно.\n"
    "Ты умеешь объяснять, планировать, помогать с ПК, кодом, проектами и локальными командами.\n"
    "Не выдумывай факты.\n"
    "Если команда требует действия на ПК, объясни что будет сделано.\n"
    "Если действие опасное или необратимое, попроси подтверждение.\n"
    "Отвечай на русском, если пользователь говорит по-русски."
)

class AIRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def plan(self, text: str, system_prompt: str | None = None) -> PlannerResult:
        sys_prompt = system_prompt or SYSTEM_PROMPT
        
        # 1. OpenRouter (Primary)
        if self.settings.openrouter_api_key:
            return self._plan_openrouter(text, sys_prompt)

        # 2. Groq (Secondary)
        if self.settings.groq_api_key:
            return self._plan_groq(text, sys_prompt)

        # 3. Controlled Fallback (when no keys are present)
        return self._plan_fallback(text)

    def _plan_openrouter(self, text: str, system_prompt: str) -> PlannerResult:
        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost/jarvis-pc-v2",
            "X-Title": "JARVIS PC V2",
        }
        payload = {
            "model": self.settings.openrouter_model or "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.4,
            "max_tokens": 600,
        }
        return self._call_completion_api(endpoint, headers, payload, "openrouter")

    def _plan_groq(self, text: str, system_prompt: str) -> PlannerResult:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.groq_model or "llama3-8b-8192",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.4,
            "max_tokens": 600,
        }
        return self._call_completion_api(endpoint, headers, payload, "groq")

    def _plan_fallback(self, text: str) -> PlannerResult:
        answer = "Сэр, AI-мозг пока не подключён: отсутствует OpenRouter API key. Локальные команды доступны."
        return PlannerResult(
            status="unavailable",
            answer_text=answer,
            actions=[],
            provider="fallback",
            error="no_api_keys",
            model="local_fallback",
            error_message="OpenRouter and Groq API keys are missing.",
            fix="Add JARVIS_OPENROUTER_API_KEY or JARVIS_GROQ_API_KEY to your .env file.",
            latency_ms=0,
            openrouter_called=False
        )

    def _call_completion_api(self, endpoint: str, headers: dict, payload: dict, provider: str) -> PlannerResult:
        started = time.perf_counter()
        try:
            timeout = httpx.Timeout(15.0, connect=5.0, read=10.0)
            with httpx.Client(timeout=timeout, trust_env=True) as client:
                response = client.post(endpoint, headers=headers, json=payload)
            
            latency_ms = int((time.perf_counter() - started) * 1000)
            status_code = response.status_code
            if status_code >= 400:
                err_msg = response.text[:200]
                return PlannerResult(
                    status="unavailable",
                    answer_text=f"AI Router {provider} error: {response.reason_phrase}",
                    actions=[],
                    provider=provider,
                    error="HTTPStatusError",
                    model=payload.get("model"),
                    status_code=status_code,
                    error_message=err_msg,
                    latency_ms=latency_ms,
                    endpoint=endpoint
                )

            data = response.json()
            choices = data.get("choices")
            if choices and len(choices) > 0:
                answer = choices[0].get("message", {}).get("content", "").strip()
                if answer:
                    return PlannerResult(
                        status="answered",
                        answer_text=answer,
                        actions=[],
                        provider=provider,
                        model=payload.get("model"),
                        status_code=status_code,
                        latency_ms=latency_ms,
                        endpoint=endpoint,
                        openrouter_called=(provider == "openrouter")
                    )

            return PlannerResult(
                status="unavailable",
                answer_text="Empty response from AI service.",
                actions=[],
                provider=provider,
                error="empty_response",
                model=payload.get("model"),
                status_code=status_code,
                latency_ms=latency_ms,
                endpoint=endpoint
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return PlannerResult(
                status="unavailable",
                answer_text=f"AI Router {provider} failed: {exc.__class__.__name__}",
                actions=[],
                provider=provider,
                error=exc.__class__.__name__,
                model=payload.get("model"),
                error_message=str(exc),
                latency_ms=latency_ms,
                endpoint=endpoint
            )

    async def ask(self, prompt: str, system_prompt: str | None = None, context: dict | None = None) -> PlannerResult:
        import anyio
        return await anyio.to_thread.run_sync(self.plan, prompt, system_prompt)
