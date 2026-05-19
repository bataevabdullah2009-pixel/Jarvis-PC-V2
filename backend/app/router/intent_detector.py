from __future__ import annotations

import re
from dataclasses import dataclass

from app.scenarios import music, news, welcome_home, workspace


PUNCTUATION_RE = re.compile(r"[,.!?;:()\[\]{}\"'«»]+")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class MatchResult:
    kind: str
    name: str
    confidence: float


def normalize_text(text: str) -> str:
    normalized = text.casefold().replace("ё", "е")
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    if normalized.startswith("джарвис "):
        without_wake = normalized.removeprefix("джарвис ").strip()
        if without_wake:
            normalized = without_wake
    return normalized


def match_scenario(normalized_text: str) -> MatchResult | None:
    scenario_triggers = {
        "welcome_home": {normalize_text(trigger) for trigger in welcome_home.TRIGGERS},
        "news": {normalize_text(trigger) for trigger in news.TRIGGERS},
        "workspace": {normalize_text(trigger) for trigger in workspace.TRIGGERS},
        "music": {normalize_text(trigger) for trigger in music.TRIGGERS},
    }

    for scenario_name, triggers in scenario_triggers.items():
        if normalized_text in triggers:
            return MatchResult("scenario", scenario_name, 1.0)

    for scenario_name, triggers in scenario_triggers.items():
        if any(trigger in normalized_text for trigger in triggers):
            return MatchResult("scenario", scenario_name, 0.82)

    return None


def match_open_app(normalized_text: str) -> str | None:
    for prefix in ("открой ", "запусти "):
        if normalized_text.startswith(prefix):
            app_name = normalized_text.removeprefix(prefix).strip()
            if app_name:
                return app_name
    return None
