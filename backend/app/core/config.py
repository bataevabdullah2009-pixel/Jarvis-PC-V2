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

DEFAULT_WAKE_WORDS = ["джарвис", "чарли", "jarvis"]
VOICE_TONES = {"calm", "serious", "fast", "cinematic", "friendly"}
VOICE_TONE_PRESETS: dict[str, str] = {
    "calm": "коротко, спокойно, уверенно",
    "serious": "строго, без лишних слов",
    "fast": "максимально коротко и быстро",
    "cinematic": "в стиле ассистента из фантастического фильма",
    "friendly": "дружелюбно, но без болтовни",
}


def _split_csv(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    else:
        items = [item.strip() for item in str(value).split(",")]
    return [item for item in items if item]


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _default_voice_profiles(main_voice_id: str | None = None, voice_id_2: str | None = None, voice_id_3: str | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id": "jarvis_main",
            "name": "Jarvis Main",
            "provider": "fish_audio",
            "voice_id": main_voice_id or "",
            "tone": "calm",
            "enabled": True,
        },
        {
            "id": "jarvis_deep",
            "name": "Jarvis Deep",
            "provider": "fish_audio",
            "voice_id": voice_id_2 or "",
            "tone": "serious",
            "enabled": True,
        },
        {
            "id": "assistant_alt",
            "name": "Assistant Alt",
            "provider": "fish_audio",
            "voice_id": voice_id_3 or "",
            "tone": "friendly",
            "enabled": True,
        },
    ]


def normalize_voice_profiles(value: Any, main_voice_id: str | None = None, voice_id_2: str | None = None, voice_id_3: str | None = None) -> list[dict[str, Any]]:
    defaults = _default_voice_profiles(main_voice_id, voice_id_2, voice_id_3)
    default_by_id = {profile["id"]: profile for profile in defaults}
    profiles: list[dict[str, Any]] = []

    if isinstance(value, list):
        for raw_profile in value:
            if not isinstance(raw_profile, dict):
                continue
            profile_id = str(raw_profile.get("id") or "").strip()
            if not profile_id:
                continue
            base = dict(default_by_id.get(profile_id, {}))
            merged = {**base, **raw_profile}
            if not merged.get("voice_id") and base.get("voice_id"):
                merged["voice_id"] = base["voice_id"]
            tone = str(merged.get("tone") or "calm").strip().lower()
            profiles.append(
                {
                    "id": profile_id,
                    "name": str(merged.get("name") or profile_id),
                    "provider": str(merged.get("provider") or "fish_audio"),
                    "voice_id": str(merged.get("voice_id") or ""),
                    "tone": tone if tone in VOICE_TONES else "calm",
                    "enabled": bool(merged.get("enabled", True)),
                }
            )

    existing_ids = {profile["id"] for profile in profiles}
    for default_profile in defaults:
        if default_profile["id"] not in existing_ids:
            profiles.append(dict(default_profile))
    return profiles


def tone_instruction(tone: str) -> str:
    return VOICE_TONE_PRESETS.get((tone or "calm").strip().lower(), VOICE_TONE_PRESETS["calm"])

ENV_PATHS_CHECKED: list[Path] = []
ENV_PATHS_LOADED: list[Path] = []
ENV_LOAD_ERRORS: dict[str, str] = {}
ENV_LOCK = threading.Lock()


def _load_env_file(path: Path, override: bool = True) -> bool:
    if not path.exists():
        return False

    try:
        try:
            from dotenv import load_dotenv

            load_dotenv(path, override=override)
        except ImportError:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if override or key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:
        ENV_LOAD_ERRORS[str(path)] = f"{exc.__class__.__name__}: {exc}"
        return False
    return True


def load_environment() -> None:
    global ENV_PATHS_CHECKED, ENV_PATHS_LOADED

    with ENV_LOCK:
        paths_to_check: list[Path] = []

        # Find JARVIS_ENV_FILE if specified
        env_file_var = os.getenv("JARVIS_ENV_FILE")
        jarvis_env_path = Path(env_file_var).resolve() if env_file_var else None

        # Determine project_root and app_current
        proj_root = Path(os.getenv("JARVIS_PROJECT_ROOT", PROJECT_ROOT)).resolve()
        
        if env_file_var:
            app_curr = Path(env_file_var).resolve().parent
        elif getattr(sys, "frozen", False):
            app_curr = Path(sys.executable).resolve().parents[2]
        else:
            app_curr = proj_root / "app_current"

        # Order of search paths:
        # 2. <project_root>\backend\.env
        paths_to_check.append(proj_root / "backend" / ".env")
        # 3. <project_root>\.env
        paths_to_check.append(proj_root / ".env")
        # 4. <app_current>\.env
        paths_to_check.append(app_curr / ".env")
        # 5. <app_current>\resources\backend\.env
        paths_to_check.append(app_curr / "resources" / "backend" / ".env")
        # 6. %APPDATA%\Jarvis PC V2\.env
        appdata = os.getenv("APPDATA")
        if appdata:
            paths_to_check.append(Path(appdata) / "Jarvis PC V2" / ".env")
        # 7. %USERPROFILE%\.jarvis_pc_v2\.env
        userprofile = os.getenv("USERPROFILE")
        if userprofile:
            paths_to_check.append(Path(userprofile) / ".jarvis_pc_v2" / ".env")

        # Deduplicate paths_to_check
        deduped = _dedupe_paths(paths_to_check)

        ENV_PATHS_CHECKED = []
        if jarvis_env_path:
            ENV_PATHS_CHECKED.append(jarvis_env_path)

        for p in deduped:
            if jarvis_env_path:
                try:
                    if p.resolve() == jarvis_env_path.resolve():
                        continue
                except OSError:
                    if p.absolute() == jarvis_env_path.absolute():
                        continue
            ENV_PATHS_CHECKED.append(p)

        ENV_PATHS_LOADED = []
        ENV_LOAD_ERRORS.clear()

        # Load order: JARVIS_ENV_FILE gets loaded first with override=True
        if jarvis_env_path and _load_env_file(jarvis_env_path, override=True):
            ENV_PATHS_LOADED.append(jarvis_env_path)

        # The rest get loaded with override=False (so higher priority files take precedence)
        for path in ENV_PATHS_CHECKED:
            if jarvis_env_path and path.resolve() == jarvis_env_path.resolve():
                continue
            if _load_env_file(path, override=False):
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
    frozen = getattr(sys, "frozen", False)
    runtime_mode = "packaged" if frozen else "dev"

    or_key = settings.openrouter_api_key
    if or_key:
        or_prefix = "sk-or-v1..." if or_key.startswith("sk-or-v1") else or_key[:8] + "..."
    else:
        or_prefix = None

    fa_key = settings.fish_audio_api_key
    fa_prefix = fa_key[:8] + "..." if fa_key else None

    fa_voice = settings.fish_audio_voice_id
    fa_voice_preview = fa_voice[:8] + "..." if fa_voice else None
    groq_key = settings.groq_api_key
    groq_prefix = groq_key[:8] + "..." if groq_key else None

    checked = [str(path) for path in _dedupe_paths(ENV_PATHS_CHECKED)]
    loaded = [str(path) for path in _dedupe_paths(ENV_PATHS_LOADED)]

    fixes = []
    if not settings.openrouter_api_key:
        fixes.append("Добавьте JARVIS_OPENROUTER_API_KEY в .env")
    if not settings.fish_audio_api_key:
        fixes.append("Добавьте JARVIS_FISH_AUDIO_API_KEY в .env")
    if not settings.fish_audio_voice_id:
        fixes.append("Добавьте JARVIS_FISH_AUDIO_VOICE_ID в .env")

    return {
        "env_loaded": bool(ENV_PATHS_LOADED),
        "runtime_mode": runtime_mode,
        "cwd": os.getcwd(),
        "project_root": str(PROJECT_ROOT),
        "backend_root": str(BACKEND_ROOT),
        "paths_checked": checked,
        "paths_loaded": loaded,
        "env_paths_checked": checked,
        "env_paths_loaded": loaded,
        "env_errors": ENV_LOAD_ERRORS,
        "openrouter": {
            "key_present": bool(settings.openrouter_api_key),
            "key_prefix": or_prefix,
            "model": settings.openrouter_model,
            "model_present": bool(settings.openrouter_model),
        },
        "groq": {
            "key_present": bool(settings.groq_api_key),
            "key_prefix": groq_prefix,
            "model": settings.groq_model,
            "model_present": bool(settings.groq_model),
        },
        "ai": {
            "primary": settings.ai_primary,
            "fallback": settings.ai_fallback,
            "allow_local_fallback": settings.ai_allow_local_fallback,
        },
        "fish_audio": {
            "key_present": bool(settings.fish_audio_api_key),
            "key_prefix": fa_prefix,
            "voice_id_present": bool(settings.fish_audio_voice_id),
            "voice_id_preview": fa_voice_preview,
        },
        "tts": {
            "primary": settings.tts_primary,
            "require_fish_audio": settings.tts_require_fish_audio,
            "fallback_enabled": settings.tts_fallback_enabled,
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
    assistant_name: str = "Джарвис"
    assistant_display_name: str = "JARVIS"
    assistant_address_style: str = "сэр"
    voice_wake_enabled: bool = True
    clap_enabled: bool = True
    runtime_mode: str = "hybrid"
    autostart_enabled: bool = False
    voice_volume: int = 70
    license_enabled: bool = False
    offline_mode: bool = False
    vosk_model_path: str = "backend\\models\\vosk-model-small-ru-0.22"
    stt_provider: str = "vosk"
    ai_primary: str = "groq"
    ai_fallback: str = "openrouter"
    ai_allow_local_fallback: bool = True
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4o-mini"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_timeout_seconds: int = 12
    groq_max_tokens: int = 180
    groq_temperature: float = 0.4
    fish_audio_api_key: str | None = None
    fish_audio_voice_id: str | None = None
    fish_audio_voice_id_2: str | None = None
    fish_audio_voice_id_3: str | None = None
    voice_profile_id: str = "jarvis_main"
    voice_profiles: list[dict[str, Any]] = field(default_factory=lambda: _default_voice_profiles())
    voice_tone: str = "calm"
    resemble_api_key: str | None = None
    resemble_project_id: str | None = None
    resemble_voice_id: str | None = None
    tts_primary: str = "fish_audio"
    tts_fallback_enabled: bool = False
    tts_fallback: str = "pyttsx3"
    tts_require_fish_audio: bool = True
    tts_timeout_seconds: int = 25
    voice_provider: str = "fish_audio"
    local_tts_provider: str = "piper"
    piper_enabled: bool = False
    piper_model_path: str = "models/piper/ru_RU.onnx"
    xtts_enabled: bool = False
    xtts_api_url: str = "http://127.0.0.1:8020"
    xtts_model_path: str = "models/xtts"
    gpt_sovits_enabled: bool = False
    gpt_sovits_api_url: str = "http://127.0.0.1:9880"
    rvc_enabled: bool = False
    rvc_api_url: str = "http://127.0.0.1:7897"
    tts_pyttsx3_voice_id: str | None = None
    tts_pyttsx3_rate: int = 175
    tts_pyttsx3_volume: float = 0.8
    listener_enabled: bool = True
    listener_autostart: bool = True
    wake_words: list[str] = field(default_factory=lambda: list(DEFAULT_WAKE_WORDS))
    listener_device_id: str = "default"
    command_record_seconds: int = 6
    cooldown_ms: int = 2500
    ignore_self_audio: bool = True
    clap_threshold: float = 0.25
    min_rms_threshold: float = 0.003
    max_triggers_per_minute: int = 6
    openrouter_max_tokens: int = 180
    openrouter_temperature: float = 0.4
    openrouter_connect_timeout: int = 10
    openrouter_read_timeout: int = 20
    openrouter_total_timeout: int = 30
    openrouter_max_retries: int = 1
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

    def selected_voice_profile(self) -> dict[str, Any]:
        for profile in self.voice_profiles:
            if profile.get("id") == self.voice_profile_id:
                return profile
        return self.voice_profiles[0] if self.voice_profiles else _default_voice_profiles()[0]

    def selected_voice_id(self) -> str:
        profile = self.selected_voice_profile()
        if profile.get("provider") == "fish_audio":
            return str(profile.get("voice_id") or "")
        return ""

    def selected_voice_provider(self) -> str:
        return str(self.selected_voice_profile().get("provider") or "text_only")

    def effective_voice_tone(self) -> str:
        profile_tone = str(self.selected_voice_profile().get("tone") or "").strip().lower()
        tone = profile_tone or self.voice_tone
        return tone if tone in VOICE_TONES else "calm"

    def address(self) -> str:
        value = (self.assistant_address_style or "").strip()
        return "" if value == "без обращения" else value

    @classmethod
    def load(cls) -> "Settings":
        load_environment()
        data = _read_json(CONFIG_DIR / "settings.json", {})
        settings = cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})

        def env_default(field_name: str, *names: str, default: str | None = None) -> str | None:
            if field_name in data:
                value = data.get(field_name)
                return str(value) if value is not None else default
            return env_value(*names, default=default)

        def env_bool_default(field_name: str, *names: str, default: bool = False) -> bool:
            if field_name in data:
                return bool(data.get(field_name))
            return env_bool(*names, default=default)

        def env_bool_override(field_name: str, *names: str, default: bool = False) -> bool:
            if env_value(*names) is not None:
                return env_bool(*names, default=default)
            if field_name in data:
                return bool(data.get(field_name))
            return default

        settings.vosk_model_path = env_value("JARVIS_VOSK_MODEL_PATH", "VOSK_MODEL_PATH", default=settings.vosk_model_path) or settings.vosk_model_path
        settings.stt_provider = env_value("JARVIS_STT_PROVIDER", default=settings.stt_provider) or settings.stt_provider
        settings.ai_primary = env_default("ai_primary", "JARVIS_AI_PRIMARY", "AI_PRIMARY", default=settings.ai_primary) or settings.ai_primary
        settings.ai_fallback = env_default("ai_fallback", "JARVIS_AI_FALLBACK", "AI_FALLBACK", default=settings.ai_fallback) or settings.ai_fallback
        settings.ai_allow_local_fallback = env_bool_default("ai_allow_local_fallback", "JARVIS_AI_ALLOW_LOCAL_FALLBACK", "AI_ALLOW_LOCAL_FALLBACK", default=settings.ai_allow_local_fallback)
        settings.assistant_name = env_default("assistant_name", "JARVIS_ASSISTANT_NAME", default=settings.assistant_name) or "Джарвис"
        settings.assistant_display_name = env_default("assistant_display_name", "JARVIS_ASSISTANT_DISPLAY_NAME", default=settings.assistant_display_name) or "JARVIS"
        settings.assistant_address_style = env_default("assistant_address_style", "JARVIS_ADDRESS_STYLE", default=settings.assistant_address_style) or "сэр"
        settings.openrouter_api_key = env_value("JARVIS_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
        settings.openrouter_model = env_value("JARVIS_OPENROUTER_MODEL", "OPENROUTER_MODEL", default=settings.openrouter_model) or settings.openrouter_model
        settings.groq_api_key = env_value("JARVIS_GROQ_API_KEY", "GROQ_API_KEY")
        settings.groq_model = env_value("JARVIS_GROQ_MODEL", "GROQ_MODEL", default=settings.groq_model) or settings.groq_model
        try:
            settings.groq_timeout_seconds = int(env_value("JARVIS_GROQ_TIMEOUT_SECONDS", "GROQ_TIMEOUT_SECONDS", default=str(settings.groq_timeout_seconds)) or settings.groq_timeout_seconds)
        except ValueError:
            settings.groq_timeout_seconds = 12
        try:
            settings.groq_max_tokens = int(env_value("JARVIS_GROQ_MAX_TOKENS", "GROQ_MAX_TOKENS", default=str(settings.groq_max_tokens)) or settings.groq_max_tokens)
        except ValueError:
            settings.groq_max_tokens = 180
        try:
            settings.groq_temperature = float(env_value("JARVIS_GROQ_TEMPERATURE", "GROQ_TEMPERATURE", default=str(settings.groq_temperature)) or settings.groq_temperature)
        except ValueError:
            settings.groq_temperature = 0.4
        settings.fish_audio_api_key = env_value("JARVIS_FISH_AUDIO_API_KEY", "FISH_AUDIO_API_KEY")
        settings.fish_audio_voice_id = env_value("JARVIS_FISH_AUDIO_VOICE_ID", "FISH_AUDIO_VOICE_ID") or settings.fish_audio_voice_id
        settings.fish_audio_voice_id_2 = env_value("JARVIS_FISH_AUDIO_VOICE_ID_2", default=settings.fish_audio_voice_id_2)
        settings.fish_audio_voice_id_3 = env_value("JARVIS_FISH_AUDIO_VOICE_ID_3", default=settings.fish_audio_voice_id_3)
        settings.voice_profile_id = env_default("voice_profile_id", "JARVIS_VOICE_PROFILE_ID", default=settings.voice_profile_id) or "jarvis_main"
        settings.voice_profiles = normalize_voice_profiles(
            data.get("voice_profiles", settings.voice_profiles),
            settings.fish_audio_voice_id,
            settings.fish_audio_voice_id_2,
            settings.fish_audio_voice_id_3,
        )
        profile_ids = {str(profile.get("id")) for profile in settings.voice_profiles}
        if settings.voice_profile_id not in profile_ids:
            settings.voice_profile_id = "jarvis_main"
        settings.voice_tone = (env_default("voice_tone", "JARVIS_VOICE_TONE", default=settings.voice_tone) or "calm").strip().lower()
        if settings.voice_tone not in VOICE_TONES:
            settings.voice_tone = "calm"
        if settings.selected_voice_provider() == "fish_audio":
            selected_voice_id = settings.selected_voice_id()
            settings.fish_audio_voice_id = selected_voice_id or None
        settings.resemble_api_key = env_value("JARVIS_RESEMBLE_API_KEY", "RESEMBLE_API_KEY")
        settings.resemble_project_id = env_value("JARVIS_RESEMBLE_PROJECT_ID", "RESEMBLE_PROJECT_ID")
        settings.resemble_voice_id = env_value("JARVIS_RESEMBLE_VOICE_ID", "RESEMBLE_VOICE_ID")
        settings.tts_primary = env_value("JARVIS_TTS_PRIMARY", "TTS_PRIMARY", default=settings.tts_primary) or settings.tts_primary
        settings.voice_provider = env_value("JARVIS_VOICE_PROVIDER", default=settings.voice_provider) or settings.voice_provider
        settings.local_tts_provider = env_value("JARVIS_LOCAL_TTS_PROVIDER", default=settings.local_tts_provider) or settings.local_tts_provider
        settings.piper_enabled = env_bool("JARVIS_PIPER_ENABLED", default=settings.piper_enabled)
        settings.piper_model_path = env_value("JARVIS_PIPER_MODEL_PATH", default=settings.piper_model_path) or settings.piper_model_path
        settings.xtts_enabled = env_bool("JARVIS_XTTS_ENABLED", default=settings.xtts_enabled)
        settings.xtts_api_url = env_value("JARVIS_XTTS_API_URL", default=settings.xtts_api_url) or settings.xtts_api_url
        settings.xtts_model_path = env_value("JARVIS_XTTS_MODEL_PATH", default=settings.xtts_model_path) or settings.xtts_model_path
        settings.gpt_sovits_enabled = env_bool("JARVIS_GPT_SOVITS_ENABLED", default=settings.gpt_sovits_enabled)
        settings.gpt_sovits_api_url = env_value("JARVIS_GPT_SOVITS_API_URL", default=settings.gpt_sovits_api_url) or settings.gpt_sovits_api_url
        settings.rvc_enabled = env_bool("JARVIS_RVC_ENABLED", default=settings.rvc_enabled)
        settings.rvc_api_url = env_value("JARVIS_RVC_API_URL", default=settings.rvc_api_url) or settings.rvc_api_url
        settings.tts_fallback = env_value("JARVIS_TTS_FALLBACK", "TTS_FALLBACK", default=settings.tts_fallback) or settings.tts_fallback
        settings.tts_fallback_enabled = env_bool("JARVIS_TTS_FALLBACK_ENABLED", "TTS_FALLBACK_ENABLED", default=settings.tts_fallback_enabled)
        settings.tts_require_fish_audio = env_bool("JARVIS_TTS_REQUIRE_FISH_AUDIO", "TTS_REQUIRE_FISH_AUDIO", "JARVIS_VOICE_LOCK", default=settings.tts_require_fish_audio)
        if settings.voice_profile.strip().lower() == "jarvis style" or settings.tts_require_fish_audio:
            settings.tts_primary = "fish_audio"
            settings.tts_require_fish_audio = True
            settings.tts_fallback_enabled = False
        try:
            settings.tts_timeout_seconds = int(env_value("TTS_TIMEOUT_SECONDS", default=str(settings.tts_timeout_seconds)) or settings.tts_timeout_seconds)
        except ValueError:
            settings.tts_timeout_seconds = 25
        settings.tts_pyttsx3_voice_id = env_value("TTS_PYTTSX3_VOICE_ID", default=settings.tts_pyttsx3_voice_id)
        try:
            settings.tts_pyttsx3_rate = int(env_value("TTS_PYTTSX3_RATE", default=str(settings.tts_pyttsx3_rate)) or settings.tts_pyttsx3_rate)
        except ValueError:
            pass
        try:
            settings.tts_pyttsx3_volume = float(env_value("TTS_PYTTSX3_VOLUME", default=str(settings.tts_pyttsx3_volume)) or settings.tts_pyttsx3_volume)
        except ValueError:
            pass

        try:
            settings.openrouter_max_tokens = int(env_value("OPENROUTER_MAX_TOKENS", default=str(settings.openrouter_max_tokens)) or settings.openrouter_max_tokens)
        except ValueError:
            pass
        try:
            settings.openrouter_temperature = float(env_value("OPENROUTER_TEMPERATURE", default=str(settings.openrouter_temperature)) or settings.openrouter_temperature)
        except ValueError:
            pass
        try:
            settings.openrouter_connect_timeout = int(env_value("OPENROUTER_CONNECT_TIMEOUT", default=str(settings.openrouter_connect_timeout)) or settings.openrouter_connect_timeout)
        except ValueError:
            pass
        try:
            settings.openrouter_read_timeout = int(env_value("OPENROUTER_READ_TIMEOUT", default=str(settings.openrouter_read_timeout)) or settings.openrouter_read_timeout)
        except ValueError:
            pass
        try:
            settings.openrouter_total_timeout = int(env_value("OPENROUTER_TOTAL_TIMEOUT", default=str(settings.openrouter_total_timeout)) or settings.openrouter_total_timeout)
        except ValueError:
            pass
        try:
            settings.openrouter_max_retries = int(env_value("OPENROUTER_MAX_RETRIES", default=str(settings.openrouter_max_retries)) or settings.openrouter_max_retries)
        except ValueError:
            pass

        settings.license_enabled = os.getenv("LICENSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        settings.allowed_folders = [settings.workspace_project_path]
        
        settings.listener_enabled = env_bool_override("listener_enabled", "JARVIS_LISTENER_ENABLED", "LISTENER_ENABLED", default=True)
        settings.listener_autostart = env_bool_override("listener_autostart", "JARVIS_LISTENER_AUTOSTART", "LISTENER_AUTOSTART", default=True)
        settings.voice_wake_enabled = env_bool_default("voice_wake_enabled", "JARVIS_VOICE_WAKE_ENABLED", "VOICE_WAKE_ENABLED", default=settings.voice_wake_enabled)
        settings.clap_enabled = env_bool_default("clap_enabled", "JARVIS_CLAP_ENABLED", "CLAP_ENABLED", default=settings.clap_enabled)
        wake_words_value: str | list[str] | None
        if "wake_words" in data:
            wake_words_value = data.get("wake_words")
        else:
            wake_words_value = env_value("JARVIS_WAKE_WORDS", "WAKE_WORDS", default=",".join(DEFAULT_WAKE_WORDS))
        settings.wake_words = _split_csv(wake_words_value) or list(DEFAULT_WAKE_WORDS)
        settings.listener_device_id = env_default("listener_device_id", "JARVIS_LISTENER_DEVICE_ID", "LISTENER_DEVICE_ID", default="default") or "default"
        try:
            settings.command_record_seconds = int(env_value("JARVIS_COMMAND_RECORD_SECONDS", "COMMAND_RECORD_SECONDS", default="6") or "6")
        except ValueError:
            settings.command_record_seconds = 6
        try:
            settings.cooldown_ms = int(env_value("JARVIS_COOLDOWN_MS", "COOLDOWN_MS", default="2500") or "2500")
        except ValueError:
            settings.cooldown_ms = 2500
        settings.ignore_self_audio = env_bool("JARVIS_IGNORE_SELF_AUDIO", "IGNORE_SELF_AUDIO", default=True)
        try:
            settings.clap_threshold = float(env_value("JARVIS_CLAP_THRESHOLD", "CLAP_THRESHOLD", default="0.25") or "0.25")
        except ValueError:
            settings.clap_threshold = 0.25
        try:
            settings.min_rms_threshold = float(env_value("JARVIS_MIN_RMS_THRESHOLD", "MIN_RMS_THRESHOLD", default="0.003") or "0.003")
        except ValueError:
            settings.min_rms_threshold = 0.003
        try:
            settings.max_triggers_per_minute = int(env_value("JARVIS_MAX_TRIGGERS_PER_MINUTE", "MAX_TRIGGERS_PER_MINUTE", default="6") or "6")
        except ValueError:
            settings.max_triggers_per_minute = 6
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
            "assistant_name": self.assistant_name,
            "assistant_display_name": self.assistant_display_name,
            "assistant_address_style": self.assistant_address_style,
            "voice_wake_enabled": self.voice_wake_enabled,
            "clap_enabled": self.clap_enabled,
            "runtime_mode": self.runtime_mode,
            "autostart_enabled": self.autostart_enabled,
            "voice_volume": self.voice_volume,
            "license_enabled": False,
            "offline_mode": self.offline_mode,
            "vosk_model_path": self.vosk_model_path,
            "stt_provider": self.stt_provider,
            "ai_primary": self.ai_primary,
            "ai_fallback": self.ai_fallback,
            "ai_allow_local_fallback": self.ai_allow_local_fallback,
            "openrouter_configured": bool(self.openrouter_api_key),
            "groq_configured": bool(self.groq_api_key),
            "groq_model": self.groq_model,
            "openrouter_model": self.openrouter_model,
            "fish_audio_configured": bool(self.fish_audio_api_key),
            "fish_audio_voice_configured": bool(self.fish_audio_voice_id),
            "fish_audio_voice_id_masked": _mask_secret(self.fish_audio_voice_id),
            "resemble_configured": bool(self.resemble_api_key),
            "resemble_project_configured": bool(self.resemble_project_id),
            "resemble_voice_configured": bool(self.resemble_voice_id),
            "tts_primary": self.tts_primary,
            "tts_fallback": self.tts_fallback,
            "tts_fallback_enabled": self.tts_fallback_enabled,
            "tts_require_fish_audio": self.tts_require_fish_audio,
            "tts_timeout_seconds": self.tts_timeout_seconds,
            "voice_provider": self.voice_provider,
            "voice_profile_id": self.voice_profile_id,
            "voice_profiles": [
                {
                    **profile,
                    "voice_id_masked": _mask_secret(str(profile.get("voice_id") or "")),
                }
                for profile in self.voice_profiles
            ],
            "voice_tone": self.voice_tone,
            "effective_voice_tone": self.effective_voice_tone(),
            "tone_instruction": tone_instruction(self.effective_voice_tone()),
            "local_tts_provider": self.local_tts_provider,
            "piper_enabled": self.piper_enabled,
            "piper_model_path": self.piper_model_path,
            "xtts_enabled": self.xtts_enabled,
            "xtts_api_url": self.xtts_api_url,
            "xtts_model_path": self.xtts_model_path,
            "gpt_sovits_enabled": self.gpt_sovits_enabled,
            "gpt_sovits_api_url": self.gpt_sovits_api_url,
            "rvc_enabled": self.rvc_enabled,
            "rvc_api_url": self.rvc_api_url,
            "listener_enabled": self.listener_enabled,
            "listener_autostart": self.listener_autostart,
            "wake_words": self.wake_words,
            "listener_device_id": self.listener_device_id,
            "command_record_seconds": self.command_record_seconds,
            "cooldown_ms": self.cooldown_ms,
            "ignore_self_audio": self.ignore_self_audio,
            "clap_threshold": self.clap_threshold,
            "min_rms_threshold": self.min_rms_threshold,
            "max_triggers_per_minute": self.max_triggers_per_minute,
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
        "ai_primary",
        "ai_fallback",
        "ai_allow_local_fallback",
        "voice_profile",
        "assistant_name",
        "assistant_display_name",
        "assistant_address_style",
        "voice_wake_enabled",
        "clap_enabled",
        "runtime_mode",
        "autostart_enabled",
        "voice_volume",
        "offline_mode",
        "listener_enabled",
        "listener_autostart",
        "listener_device_id",
        "wake_words",
        "voice_profile_id",
        "voice_profiles",
        "voice_tone",
    }
    current = _read_json(CONFIG_DIR / "settings.json", {})
    for key, value in patch.items():
        if key in editable:
            if key == "wake_words":
                value = _split_csv(value) or list(DEFAULT_WAKE_WORDS)
            elif key == "voice_profiles":
                value = normalize_voice_profiles(value)
            elif key == "voice_tone":
                value = str(value).strip().lower()
                if value not in VOICE_TONES:
                    value = "calm"
            current[key] = value

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with (CONFIG_DIR / "settings.json").open("w", encoding="utf-8", newline="\n") as file:
        json.dump(current, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return Settings.load()
