from __future__ import annotations

from app.core.config import Settings
from app.providers.openrouter import OpenRouterPlanner, PlannerResult


class AIPlanner:
    def __init__(self, settings: Settings) -> None:
        self.provider = OpenRouterPlanner(settings)

    def plan(self, text: str) -> PlannerResult:
        return self.provider.plan(text)

