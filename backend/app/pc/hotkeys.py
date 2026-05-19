from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_RETURN = 0x0D


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


def _send_virtual_key(vk_code: int) -> None:
    extra = ctypes.pointer(wintypes.ULONG(0))
    inputs = (INPUT * 2)(
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk_code, 0, 0, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, extra)),
    )
    sent = ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))  # type: ignore[attr-defined]
    if sent != 2:
        raise OSError("SendInput failed")


def send_media_play_pause(*, dry_run: bool = False, delay_seconds: float = 0) -> dict[str, Any]:
    if dry_run:
        return {
            "type": "hotkey",
            "target": "media_play_pause",
            "status": "dry_run",
        }

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    try:
        _send_virtual_key(VK_MEDIA_PLAY_PAUSE)
    except Exception as exc:
        return {
            "type": "hotkey",
            "target": "media_play_pause",
            "status": "failed",
            "message": exc.__class__.__name__,
        }

    return {
        "type": "hotkey",
        "target": "media_play_pause",
        "status": "completed",
    }


def send_enter(*, dry_run: bool = False, delay_seconds: float = 0) -> dict[str, Any]:
    if dry_run:
        return {
            "type": "hotkey",
            "target": "enter",
            "status": "dry_run",
        }

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    try:
        _send_virtual_key(VK_RETURN)
    except Exception as exc:
        return {
            "type": "hotkey",
            "target": "enter",
            "status": "failed",
            "message": exc.__class__.__name__,
        }

    return {
        "type": "hotkey",
        "target": "enter",
        "status": "completed",
    }

