from __future__ import annotations

import os
import re
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List
from app.core.config import PROJECT_ROOT, get_settings
from app.events.websocket_bus import event_bus

logger = logging.getLogger("jarvis.reminders")

REMINDERS_FILE = PROJECT_ROOT / "data" / "reminders.json"


def _word_to_digit(text: str) -> str:
    """Converts common Russian number words to digits for simpler regex parsing."""
    replacements = {
        "одну": "1", "один": "1",
        "две": "2", "два": "2",
        "три": "3",
        "четыре": "4",
        "пять": "5",
        "шесть": "6",
        "семь": "7",
        "восемь": "8",
        "девять": "9",
        "десять": "10",
    }
    words = text.split()
    converted = []
    for w in words:
        low_w = w.lower()
        if low_w in replacements:
            converted.append(replacements[low_w])
        else:
            converted.append(w)
    return " ".join(converted)


class ReminderService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        
        # Ensure persistence directory exists
        REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("[REMINDER] Reminder service scheduler started.")

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def load_reminders(self) -> list[dict[str, Any]]:
        with self._lock:
            if not REMINDERS_FILE.exists():
                return []
            try:
                with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("[REMINDER] Failed to load reminders: %s", e)
                return []

    def save_reminders(self, reminders: list[dict[str, Any]]) -> None:
        with self._lock:
            try:
                with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(reminders, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("[REMINDER] Failed to save reminders: %s", e)

    def add_reminder(self, text: str, delay_seconds: int) -> dict[str, Any]:
        reminders = self.load_reminders()
        now = time.time()
        due_at = now + delay_seconds
        
        reminder = {
            "id": f"rem_{int(now)}_{len(reminders)}",
            "text": text,
            "created_at": datetime.fromtimestamp(now).isoformat(),
            "due_at": datetime.fromtimestamp(due_at).isoformat(),
            "due_timestamp": due_at,
            "fired": False
        }
        reminders.append(reminder)
        self.save_reminders(reminders)
        
        logger.info("[REMINDER] Added reminder id=%s due in %ds: '%s'", reminder["id"], delay_seconds, text)
        event_bus.emit("assistant.reminder.created", reminder)
        return reminder

    def parse_and_create(self, query: str) -> dict[str, Any] | None:
        """
        Parses commands like:
        - "напомни мне через две часа проверить ..."
        - "напомни через 10 минут выпить воды"
        - "поставь таймер на 5 минут"
        """
        clean_q = _word_to_digit(query)
        logger.info("[REMINDER] Parsing query: '%s' (cleaned: '%s')", query, clean_q)

        # Regex patterns
        # 1. "напомни (мне)? (через)? (\d+) (минут|час|секунд) (.*)"
        remind_pattern = re.compile(
            r"напомни(?:\s+мне)?(?:\s+через)?\s+(\d+)\s+(минут[ыа]?|час[ао]в|секунд[ыа]?|м|ч|с)\s+(?:чтобы\s+|что\s+)?(.*)",
            re.IGNORECASE
        )
        
        # 2. "поставь таймер на (\d+) (минут|час|секунд)"
        timer_pattern = re.compile(
            r"поставь\s+таймер\s+на\s+(\d+)\s+(минут[ыа]?|час[ао]в|секунд[ыа]?|м|ч|с)(?:\s+(.*))?",
            re.IGNORECASE
        )

        match = remind_pattern.search(clean_q)
        if not match:
            match = timer_pattern.search(clean_q)
            is_timer = True
        else:
            is_timer = False

        if not match:
            return None

        val = int(match.group(1))
        unit = match.group(2).lower()
        
        # Determine reminder content text
        if is_timer:
            rem_text = match.group(3) or "Таймер истек!"
        else:
            rem_text = match.group(3)

        rem_text = rem_text.strip()
        
        # Calculate delay seconds
        delay = val
        if "минут" in unit or unit == "м":
            delay = val * 60
        elif "час" in unit or unit == "ч":
            delay = val * 3600
        elif "секунд" in unit or unit == "с":
            delay = val

        return self.add_reminder(rem_text, delay)

    def _run_loop(self) -> None:
        while self._running:
            try:
                reminders = self.load_reminders()
                now = time.time()
                changed = False
                
                for r in reminders:
                    if not r.get("fired", False) and r.get("due_timestamp", 0) <= now:
                        r["fired"] = True
                        changed = True
                        logger.info("[REMINDER] Reminder due! id=%s text='%s'", r["id"], r["text"])
                        
                        # 1. Emit EventBus event
                        event_bus.emit("assistant.reminder.due", r)
                        
                        # 2. Speak it asynchronously using TTSService
                        from app.voice.tts import TTSService
                        tts_text = f"Сэр, напоминаю: {r['text']}"
                        
                        # Use a background thread for speech so we don't block the scheduler
                        def run_speech():
                            try:
                                tts = TTSService(get_settings())
                                tts.speak(tts_text, blocking=True)
                            except Exception as ex:
                                logger.error("[REMINDER] Failed to announce reminder: %s", ex)
                        
                        threading.Thread(target=run_speech, daemon=True).start()

                if changed:
                    self.save_reminders(reminders)
            except Exception as e:
                logger.error("[REMINDER] Exception in scheduler loop: %s", e)
            
            time.sleep(1.0)


# Initialize global instance
reminder_service = ReminderService()
