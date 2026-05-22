from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _resolve_backend_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BACKEND_ROOT = _resolve_backend_root()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path.absolute()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def _candidate_project_roots() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("JARVIS_PROJECT_ROOT", "PORTABLE_EXECUTABLE_DIR"):
        value = os.getenv(env_name)
        if value:
            candidates.append(Path(value))

    candidates.extend(
        [
            Path.cwd(),
            Path.cwd().parent,
            Path.cwd().parent.parent,
            BACKEND_ROOT.parent,
            BACKEND_ROOT.parent.parent,
            BACKEND_ROOT,
        ]
    )

    executable = Path(sys.executable).resolve()
    candidates.extend([executable.parent, executable.parent.parent])
    return _dedupe_paths(candidates)


def _resolve_project_root() -> Path:
    for root in _candidate_project_roots():
        if (root / ".env").exists():
            return root
        if (root / "backend" / ".env").exists():
            return root
    for root in _candidate_project_roots():
        if (root / "backend").exists() and (root / "frontend").exists():
            return root
    return BACKEND_ROOT.parent


PROJECT_ROOT = _resolve_project_root()
CONFIG_DIR = BACKEND_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"

ENV_PATHS_CHECKED: list[Path] = []
ENV_PATHS_LOADED: list[Path] = []
ENV_LOAD_ERRORS: dict[str, str] = {}
ENV_LOCK = threading.Lock()


def _load_env_file(path: Path) -> bool:
    if not path.exists():
        return False

    try:
        try:
            from dotenv import load_dotenv

            load_dotenv(path, override=True)
        except ImportError:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value
    except Exception as exc:
        ENV_LOAD_ERRORS[str(path)] = f"{exc.__class__.__name__}: {exc}"
        return False
    return True


def load_environment() -> None:
    global ENV_PATHS_CHECKED, ENV_PATHS_LOADED

    with ENV_LOCK:
        base_paths: list[Path] = [
            PROJECT_ROOT / ".env",
            Path.cwd() / ".env",
        ]
        for root in _candidate_project_roots():
            base_paths.append(root / ".env")

        backend_paths: list[Path] = [
            PROJECT_ROOT / "backend" / ".env",
        ]
        for root in _candidate_project_roots():
            backend_paths.append(root / "backend" / ".env")

        ENV_PATHS_CHECKED = _dedupe_paths(base_paths) + _dedupe_paths(backend_paths)
        ENV_PATHS_LOADED = []
        ENV_LOAD_ERRORS.clear()
        for path in ENV_PATHS_CHECKED:
            if _load_env_file(path):
                ENV_PATHS_LOADED.append(path)


def env_value(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def env_bool(*names: str, default: bool = False) -> bool:
    value = env_value(*names)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_debug_status(settings: "Settings") -> dict[str, Any]:
    def prefix(value: str | None, length: int = 12) -> str | None:
        if not value:
            return None
        if len(value) <= length:
            return value
        return value[:length] + "..."

    checked = [str(path) for path in _dedupe_paths(ENV_PATHS_CHECKED)]
    loaded = [str(path) for path in _dedupe_paths(ENV_PATHS_LOADED)]

    fixes = []
    if not settings.openrouter_api_key:
        fixes.append("Добавьте JARVIS_OPENROUTER_API_KEY в C:\\Jarvis PC V2\\backend\\.env")
    if not settings.openrouter_model:
        fixes.append("Добавьте JARVIS_OPENROUTER_MODEL в C:\\Jarvis PC V2\\backend\\.env")
    if not settings.fish_audio_api_key:
        fixes.append("Добавьте JARVIS_FISH_AUDIO_API_KEY в C:\\Jarvis PC V2\\backend\\.env")
    if not settings.fish_audio_voice_id:
        fixes.append("Добавьте JARVIS_FISH_AUDIO_VOICE_ID в C:\\Jarvis PC V2\\backend\\.env")

    return {
        "env_loaded": bool(ENV_PATHS_LOADED),
        "paths_checked": checked,
        "paths_loaded": loaded,
        "env_paths_checked": checked,
        "env_paths_loaded": loaded,
        "env_errors": ENV_LOAD_ERRORS,
        "openrouter": {
            "key_present": bool(settings.openrouter_api_key),
            "key_prefix": prefix(settings.openrouter_api_key, 12),
            "model": settings.openrouter_model,
            "model_present": bool(settings.openrouter_model),
            "missing_variable": None if settings.openrouter_api_key else "JARVIS_OPENROUTER_API_KEY or OPENROUTER_API_KEY",
        },
        "fish_audio": {
            "key_present": bool(settings.fish_audio_api_key),
            "key_prefix": prefix(settings.fish_audio_api_key, 8),
            "voice_id_present": bool(settings.fish_audio_voice_id),
            "voice_id_prefix": prefix(settings.fish_audio_voice_id, 8),
            "missing_key_variable": None if settings.fish_audio_api_key else "JARVIS_FISH_AUDIO_API_KEY or FISH_AUDIO_API_KEY",
            "missing_voice_id_variable": None if settings.fish_audio_voice_id else "JARVIS_FISH_AUDIO_VOICE_ID or FISH_AUDIO_VOICE_ID",
        },
        "tts": {
            "primary": settings.tts_primary,
            "fallback": settings.tts_fallback,
            "fallback_enabled": settings.tts_fallback_enabled,
            "require_fish_audio": settings.tts_require_fish_audio,
            "timeout_seconds": settings.tts_timeout_seconds,
        },
        "fixes": fixes,
    }


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


@dataclass(slots=True)
class Settings:
    app_name: str = "JARVIS PC V2"
    version: str = "0.1.0"
    phase: str = "phase-1"
    debug_mode: bool = False
    chatgpt_url: str = "https://chatgpt.com"
    news_url: str = "https://news.google.com/topstories?hl=ru&gl=RU&ceid=RU:ru"
    news_rss_url: str = "https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru"
    kion_music_search_url: str = "https://music.kion.ru/search?text={query}"
    workspace_project_path: str = r"C:\Jarvis\jarvis-car"
    open_terminal_with_workspace: bool = False
    voice_profile: str = "Jarvis style"
    voice_wake_enabled: bool = False
    clap_enabled: bool = False
    runtime_mode: str = "hybrid"
    autostart_enabled: bool = False
    voice_volume: int = 70
    license_enabled: bool = False
    offline_mode: bool = False
    vosk_model_path: str = "backend\\models\\vosk-model-small-ru-0.22"
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4o-mini"
    groq_api_key: str | None = None
    groq_model: str = "llama3-8b-8192"
    fish_audio_api_key: str | None = None
    fish_audio_voice_id: str | None = None
    resemble_api_key: str | None = None
    resemble_project_id: str | None = None
    resemble_voice_id: str | None = None
    tts_primary: str = "fish_audio"
    tts_fallback_enabled: bool = True
    tts_fallback: str = "pyttsx3"
    tts_require_fish_audio: bool = False
    tts_timeout_seconds: int = 25
    allowed_apps: dict[str, list[str]] = field(
        default_factory=lambda: {
            "telegram": ["telegram", "Telegram.exe"],
            "телеграм": ["telegram", "Telegram.exe"],
            "discord": ["discord", "Discord.exe"],
            "дискорд": ["discord", "Discord.exe"],
            "vs code": ["code", "Code.exe"],
            "vscode": ["code", "Code.exe"],
            "visual studio code": ["code", "Code.exe"],
            "browser": ["start"],
            "браузер": ["start"],
            "explorer": ["explorer"],
            "проводник": ["explorer"],
            "taskmgr": ["taskmgr"],
            "диспетчер задач": ["taskmgr"],
        }
    )
    allowed_folders: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        load_environment()
        data = _read_json(CONFIG_DIR / "settings.json", {})
        settings = cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})
        settings.openrouter_api_key = env_value("JARVIS_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
        settings.openrouter_model = env_value("JARVIS_OPENROUTER_MODEL", "OPENROUTER_MODEL", default=settings.openrouter_model) or settings.openrouter_model
        settings.groq_api_key = env_value("JARVIS_GROQ_API_KEY", "GROQ_API_KEY")
        settings.groq_model = env_value("JARVIS_GROQ_MODEL", "GROQ_MODEL", default=settings.groq_model) or settings.groq_model
        settings.fish_audio_api_key = env_value("JARVIS_FISH_AUDIO_API_KEY", "FISH_AUDIO_API_KEY")
        settings.fish_audio_voice_id = env_value("JARVIS_FISH_AUDIO_VOICE_ID", "FISH_AUDIO_VOICE_ID")
        settings.resemble_api_key = env_value("JARVIS_RESEMBLE_API_KEY", "RESEMBLE_API_KEY")
        settings.resemble_project_id = env_value("JARVIS_RESEMBLE_PROJECT_ID", "RESEMBLE_PROJECT_ID")
        settings.resemble_voice_id = env_value("JARVIS_RESEMBLE_VOICE_ID", "RESEMBLE_VOICE_ID")
        settings.tts_primary = env_value("TTS_PRIMARY", default=settings.tts_primary) or settings.tts_primary
        settings.tts_fallback = env_value("TTS_FALLBACK", default=settings.tts_fallback) or settings.tts_fallback
        settings.tts_fallback_enabled = env_bool("TTS_FALLBACK_ENABLED", default=settings.tts_fallback_enabled)
        settings.tts_require_fish_audio = env_bool("TTS_REQUIRE_FISH_AUDIO", default=settings.tts_require_fish_audio)
        try:
            settings.tts_timeout_seconds = int(env_value("TTS_TIMEOUT_SECONDS", default=str(settings.tts_timeout_seconds)) or settings.tts_timeout_seconds)
        except ValueError:
            settings.tts_timeout_seconds = 25
        settings.license_enabled = os.getenv("LICENSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        settings.allowed_folders = [settings.workspace_project_path]
        return settings

    def sanitized(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "version": self.version,
            "phase": self.phase,
            "debug_mode": self.debug_mode,
            "chatgpt_url": self.chatgpt_url,
            "news_url": self.news_url,
            "news_rss_url": self.news_rss_url,
            "workspace_project_path": self.workspace_project_path,
            "voice_profile": self.voice_profile,
            "voice_wake_enabled": self.voice_wake_enabled,
            "clap_enabled": self.clap_enabled,
            "runtime_mode": self.runtime_mode,
            "autostart_enabled": self.autostart_enabled,
            "voice_volume": self.voice_volume,
            "license_enabled": False,
            "offline_mode": self.offline_mode,
            "vosk_model_path": self.vosk_model_path,
            "openrouter_configured": bool(self.openrouter_api_key),
            "groq_configured": bool(self.groq_api_key),
            "fish_audio_configured": bool(self.fish_audio_api_key),
            "fish_audio_voice_configured": bool(self.fish_audio_voice_id),
            "resemble_configured": bool(self.resemble_api_key),
            "resemble_project_configured": bool(self.resemble_project_id),
            "resemble_voice_configured": bool(self.resemble_voice_id),
            "tts_primary": self.tts_primary,
            "tts_fallback": self.tts_fallback,
            "tts_fallback_enabled": self.tts_fallback_enabled,
            "tts_require_fish_audio": self.tts_require_fish_audio,
            "tts_timeout_seconds": self.tts_timeout_seconds,
        }


def get_settings() -> Settings:
    return Settings.load()


def patch_settings(patch: dict[str, Any]) -> Settings:
    editable = {
        "debug_mode",
        "chatgpt_url",
        "news_url",
        "news_rss_url",
        "workspace_project_path",
        "open_terminal_with_workspace",
        "voice_profile",
        "voice_wake_enabled",
        "clap_enabled",
        "runtime_mode",
        "autostart_enabled",
        "voice_volume",
        "offline_mode",
    }
    current = _read_json(CONFIG_DIR / "settings.json", {})
    for key, value in patch.items():
        if key in editable:
            current[key] = value

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with (CONFIG_DIR / "settings.json").open("w", encoding="utf-8") as file:
        json.dump(current, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return Settings.load()
