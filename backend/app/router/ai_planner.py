from __future__ import annotations

import anyio
from typing import Any
from app.core.config import Settings
from app.providers.openrouter import PlannerResult, OpenRouterPlanner


class AIPlanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.openrouter = OpenRouterPlanner(settings)

    def plan(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        """Execute synchronous plan detection."""
        if not self.settings.openrouter_api_key:
            warning_text = "Сэр, AI-мозг пока не подключён: отсутствует OpenRouter API key. Локальные команды работают."
            return PlannerResult(
                status="ai_limited",
                answer_text=warning_text,
                actions=[],
                provider="openrouter",
                error="openrouter_key_missing",
                model=self.settings.openrouter_model,
                error_type="openrouter_key_missing",
                error_message="OpenRouter API key is missing.",
                fix="Добавьте JARVIS_OPENROUTER_API_KEY в .env",
                latency_ms=0,
                openrouter_called=False
            )

        try:
            result = self.openrouter.plan(text, context)
        except TypeError:
            result = self.openrouter.plan(text)

        if result.status == "unavailable":
            return PlannerResult(
                status="ai_error",
                answer_text=result.answer_text,
                actions=[],
                provider="openrouter",
                error=result.error or "provider_error",
                model=result.model,
                status_code=result.status_code,
                error_type=result.error_type or "provider_error",
                error_message=result.error_message or result.answer_text,
                fix=result.fix,
                latency_ms=result.latency_ms,
                retry_count=result.retry_count,
                endpoint=result.endpoint,
                openrouter_called=result.openrouter_called,
                raw_response_preview=result.raw_response_preview,
                response_text_preview=result.response_text_preview
            )

        return result

    async def ask(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        """Execute asynchronous ask/query."""
        return await anyio.to_thread.run_sync(self.plan, text, context)

    def test(self, text: str) -> dict[str, Any]:
        """Execute diagnostic connection test."""
        return self.openrouter.test(text)
