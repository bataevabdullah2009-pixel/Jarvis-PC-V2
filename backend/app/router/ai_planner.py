from __future__ import annotations

import anyio
from typing import Any

from app.core.config import Settings
from app.providers.groq import GroqPlanner
from app.providers.openrouter import OpenRouterPlanner, PlannerResult


LOCAL_AI_FALLBACK_TEXT = "Сэр, облачный AI сейчас недоступен. Локальные команды доступны."


class AIPlanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.groq = GroqPlanner(settings)
        self.openrouter = OpenRouterPlanner(settings)

    def plan(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        """Route AI requests through primary, fallback, then local text fallback."""
        context = context or {}
        results: list[PlannerResult] = []

        for provider in self._provider_order():
            result = self._call_provider(provider, text, context)
            results.append(result)
            if result.status == "answered":
                return result

        last = results[-1] if results else None
        total_latency_ms = sum(result.latency_ms or 0 for result in results)
        openrouter_called = any(result.openrouter_called for result in results)

        if self.settings.ai_allow_local_fallback:
            return PlannerResult(
                status="ai_limited",
                answer_text=LOCAL_AI_FALLBACK_TEXT,
                actions=[],
                provider="text_only",
                error=last.error if last else "ai_unavailable",
                model=last.model if last else None,
                status_code=last.status_code if last else None,
                error_type=last.error_type if last else "ai_unavailable",
                error_message=last.error_message if last else "No AI providers configured.",
                fix=last.fix if last else "Добавьте JARVIS_GROQ_API_KEY или JARVIS_OPENROUTER_API_KEY в .env.",
                latency_ms=total_latency_ms,
                endpoint=last.endpoint if last else None,
                openrouter_called=openrouter_called,
            )

        return PlannerResult(
            status="ai_error",
            answer_text=last.answer_text if last else LOCAL_AI_FALLBACK_TEXT,
            actions=[],
            provider=last.provider if last else "text_only",
            error=last.error if last else "ai_unavailable",
            model=last.model if last else None,
            status_code=last.status_code if last else None,
            error_type=last.error_type if last else "ai_unavailable",
            error_message=last.error_message if last else "No AI providers configured.",
            fix=last.fix if last else "Добавьте AI provider key в .env.",
            latency_ms=total_latency_ms,
            endpoint=last.endpoint if last else None,
            openrouter_called=openrouter_called,
        )

    async def ask(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        """Execute asynchronous ask/query."""
        return await anyio.to_thread.run_sync(self.plan, text, context)

    def test(self, text: str) -> dict[str, Any]:
        """Execute diagnostic connection test for the configured primary provider."""
        return self.groq.test(text) if self.settings.ai_primary == "groq" else self.openrouter.test(text)

    def _provider_order(self) -> list[str]:
        order: list[str] = []
        for provider in (self.settings.ai_primary, self.settings.ai_fallback):
            name = (provider or "").strip().lower()
            if name in {"groq", "openrouter"} and name not in order:
                order.append(name)
        return order or ["groq", "openrouter"]

    def _call_provider(self, provider: str, text: str, context: dict[str, Any]) -> PlannerResult:
        if provider == "groq":
            return self.groq.plan(text, context)
        return self.openrouter.plan(text, context)
