from app.core.config import get_settings
from app.core.safety import SafetyService


def test_open_url_allowed() -> None:
    decision = SafetyService(get_settings()).validate({"type": "open_url", "target": "https://example.com"})
    assert decision.allowed is True
    assert decision.requires_confirmation is False


def test_telegram_allowlist_allowed() -> None:
    decision = SafetyService(get_settings()).validate({"type": "open_app", "target": "telegram"})
    assert decision.allowed is True


def test_shutdown_requires_confirmation() -> None:
    decision = SafetyService(get_settings()).validate({"type": "shutdown", "target": ""})
    assert decision.requires_confirmation is True
    assert decision.allowed is False


def test_dangerous_shell_forbidden() -> None:
    decision = SafetyService(get_settings()).validate({"type": "run_shell", "target": "rm -rf C:\\"})
    assert decision.forbidden is True

