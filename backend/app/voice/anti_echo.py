from __future__ import annotations

import re
import time
import difflib
import logging
from typing import Any
from app.core.config import get_settings
from app.events.websocket_bus import event_bus

logger = logging.getLogger("jarvis.anti_echo")

# Module level state variables
_speaking: bool = False
_cooldown_until: float = 0.0
_last_tts_text: str = ""
_consecutive_echo_count: int = 0
_self_echo_loop_triggered: bool = False


def mark_tts_started(text: str) -> None:
    """Marks that TTS playback has started."""
    global _speaking, _last_tts_text, _self_echo_loop_triggered
    _speaking = True
    _last_tts_text = text or ""
    logger.info("[ANTI-ECHO] TTS started: '%s'", _last_tts_text[:60])
    event_bus.emit("assistant.tts.started", {"text": _last_tts_text})


def mark_tts_completed(text: str) -> None:
    """Marks that TTS playback has completed and starts the cooldown period."""
    global _speaking, _cooldown_until, _last_tts_text
    _speaking = False
    if text:
        _last_tts_text = text
    
    settings = get_settings()
    cooldown_sec = float(settings.cooldown_ms) / 1000.0
    _cooldown_until = time.time() + cooldown_sec
    logger.info("[ANTI-ECHO] TTS completed. Cooldown initiated for %.1fs: '%s'", cooldown_sec, _last_tts_text[:60])
    
    event_bus.emit("assistant.tts.completed", {"text": _last_tts_text})
    event_bus.emit("listener.cooldown.started", {"duration_ms": settings.cooldown_ms})


def mark_tts_failed(text: str, error: str) -> None:
    """Handles speech playback failure gracefully."""
    global _speaking, _cooldown_until
    _speaking = False
    settings = get_settings()
    cooldown_sec = float(settings.cooldown_ms) / 1000.0
    _cooldown_until = time.time() + cooldown_sec
    logger.warning("[ANTI-ECHO] TTS failed: %s. Releasing speaking flag with cooldown.", error)
    
    event_bus.emit("assistant.tts.failed", {"text": text, "error": error})
    event_bus.emit("listener.cooldown.started", {"duration_ms": settings.cooldown_ms})


def is_speaking_now() -> bool:
    """Checks whether the assistant is currently speaking or in cooldown."""
    return _speaking or (time.time() < _cooldown_until)


def normalize_text(text: str) -> str:
    """Normalizes text for robust similarity comparison."""
    if not text:
        return ""
    # Convert to lowercase
    t = text.lower()
    # Replace common cyrillic/latin character mixes if any, strip non-alphanumeric chars
    t = re.sub(r"[^\w\s]", "", t)
    # Replace multiple spaces with a single one
    t = " ".join(t.split())
    return t


def similarity(a: str, b: str) -> float:
    """Computes the similarity ratio between two texts."""
    norm_a = normalize_text(a)
    norm_b = normalize_text(b)
    if not norm_a or not norm_b:
        return 0.0
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def should_ignore_transcript(transcript: str) -> dict[str, Any]:
    """
    Checks if the transcript should be ignored to prevent audio echo.
    Returns a dict with key indicators.
    """
    global _consecutive_echo_count, _self_echo_loop_triggered
    
    if not transcript:
        return {
            "ignore": True,
            "reason": "empty",
            "self_echo_blocked": False,
            "stop_listener": False
        }

    # 1. Check if speaking now (or in cooldown)
    if is_speaking_now():
        return {
            "ignore": True,
            "reason": "speaking_active",
            "self_echo_blocked": False,
            "stop_listener": False
        }

    # 2. Similarity comparison against last TTS output
    sim_ratio = similarity(transcript, _last_tts_text)
    norm_transcript = normalize_text(transcript)
    norm_tts = normalize_text(_last_tts_text)

    is_similar = sim_ratio > 0.60
    
    # 3. Check if transcript contains major part of the last TTS reply
    contains_tts_substring = False
    if len(norm_tts) > 10 and len(norm_transcript) > 10:
        if norm_tts in norm_transcript or norm_transcript in norm_tts:
            contains_tts_substring = True

    if is_similar or contains_tts_substring:
        _consecutive_echo_count += 1
        logger.warning(
            "[ANTI-ECHO] Echo detected! similarity=%.2f substring=%s. Consecutive count: %d. Transcript='%s', Last TTS='%s'",
            sim_ratio, contains_tts_substring, _consecutive_echo_count, transcript, _last_tts_text
        )
        
        stop_listener = False
        if _consecutive_echo_count >= 3:
            _self_echo_loop_triggered = True
            stop_listener = True
            logger.critical("[ANTI-ECHO] Self-echo loop detected 3 times consecutively! Signalling listener stop.")

        return {
            "ignore": True,
            "reason": f"similarity_echo (ratio: {sim_ratio:.2f})",
            "self_echo_blocked": True,
            "stop_listener": stop_listener
        }

    # Reset counter on successful fresh command
    _consecutive_echo_count = 0
    return {
        "ignore": False,
        "reason": None,
        "self_echo_blocked": False,
        "stop_listener": False
    }


def check_loopback_device(device_name: str) -> bool:
    """Returns True if the selected audio device is likely a loopback/stereo mix device."""
    if not device_name:
        return False
    dn = device_name.lower()
    suspicious_patterns = ["stereo mix", "стерео микшер", "mixed capture", "loopback", "what u hear"]
    return any(p in dn for p in suspicious_patterns)
