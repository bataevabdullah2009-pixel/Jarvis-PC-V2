from app.core.config import Settings, get_settings
from app.voice.tts import TTSService


def test_tts_dry_run_uses_configured_provider_without_speaking() -> None:
    settings = Settings()
    settings.fish_audio_api_key = "fish_key"
    settings.fish_audio_voice_id = "fish_voice"
    settings.tts_primary = "fish_audio"
    settings.tts_require_fish_audio = True
    settings.tts_fallback_enabled = False
    result = TTSService(settings).speak("Тест", dry_run=True)
    assert result["status"] == "dry_run"
    assert result["spoken"] is False
    assert result["mode"] == "fish_audio"
    assert result["fallback_used"] is False


def test_command_router_dry_run_does_not_speak() -> None:
    from app.router.command_router import CommandRouter

    settings = get_settings()
    settings.fish_audio_api_key = settings.fish_audio_api_key or "fish_key"
    settings.fish_audio_voice_id = settings.fish_audio_voice_id or "fish_voice"
    result = CommandRouter(settings).handle("Джарвис, открой музыку", context={"dry_run": True})
    assert result["tts"]["status"] == "dry_run"
    assert result["spoken"] is False
