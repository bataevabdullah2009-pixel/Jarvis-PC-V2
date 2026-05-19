from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env()
    required = [
        "JARVIS_OPENROUTER_API_KEY",
        "JARVIS_FISH_AUDIO_API_KEY",
        "JARVIS_FISH_AUDIO_VOICE_ID",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print("Missing:", ", ".join(missing))
        return 1
    print("Environment looks ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

