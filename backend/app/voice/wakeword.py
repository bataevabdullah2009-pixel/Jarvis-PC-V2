from __future__ import annotations

import re
from typing import Any


_PREFIX_WORDS = {
    "\u044d\u0439",
    "hey",
    "\u043e\u043a",
    "okay",
    "\u0441\u043b\u0443\u0448\u0430\u0439",
    "\u043d\u0443",
    "СЌР№",
    "РѕРє",
    "СЃР»СѓС€Р°Р№",
    "РЅСѓ",
}


def normalize_text(text: str) -> str:
    value = (text or "").strip().lower()
    value = value.replace("\u0451", "\u0435").replace("С‘", "Рµ")
    value = re.sub(r"[^\w\s-]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _normalize_words(wake_words: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if wake_words is None:
        return []
    if isinstance(wake_words, str):
        raw_words = wake_words.split(",")
    else:
        raw_words = list(wake_words)
    normalized = [normalize_text(str(word)) for word in raw_words]
    return [word for word in normalized if word]


def extract_wake_command(transcript: str, wake_words: list[str]) -> dict[str, Any]:
    normalized = normalize_text(transcript)
    if not normalized:
        return {
            "triggered": False,
            "wake_word": None,
            "command_text": "",
            "reason": "no_wake_word",
        }

    words = _normalize_words(wake_words)
    for wake_word in words:
        pattern = rf"(?:^|\s){re.escape(wake_word)}(?:\s|$)"
        match = re.search(pattern, normalized, flags=re.UNICODE)
        if not match:
            continue

        before = normalized[: match.start()].strip()
        if before:
            before_words = before.split()
            if any(word not in _PREFIX_WORDS for word in before_words):
                continue

        command_text = normalized[match.end() :].strip()
        return {
            "triggered": True,
            "wake_word": wake_word,
            "command_text": command_text,
            "reason": "wake_word_found" if command_text else "empty_command",
        }

    return {
        "triggered": False,
        "wake_word": None,
        "command_text": "",
        "reason": "no_wake_word",
    }
