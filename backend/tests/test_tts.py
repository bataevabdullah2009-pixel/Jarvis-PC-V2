from app.core.config import get_settings
from app.voice.tts import TTSService


def test_tts_dry_run_uses_configured_provider_without_speaking() -> None:
    result = TTSService(get_settings()).speak("Тест", dry_run=True)
    assert result["status"] == "dry_run"
    assert result["spoken"] is False
    assert result["mode"] == "fish_audio"
    assert result["fallback_used"] is False


def test_command_router_dry_run_does_not_speak() -> None:
    from app.router.command_router import CommandRouter

    result = CommandRouter(get_settings()).handle("Джарвис, открой музыку", context={"dry_run": True})
    assert result["tts"]["status"] == "dry_run"
    assert result["spoken"] is False
