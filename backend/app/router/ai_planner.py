from __future__ import annotations

from typing import Any
from app.core.config import Settings
from app.providers.openrouter import PlannerResult
from app.router.ai_router import AIRouter


class AIPlanner:
    def __init__(self, settings: Settings) -> None:
        self.provider = AIRouter(settings)

    def plan(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        """Execute synchronous plan detection."""
        return self.provider.plan(text)

    async def ask(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        """Execute asynchronous ask/query."""
        return await self.provider.ask(text, context=context)
