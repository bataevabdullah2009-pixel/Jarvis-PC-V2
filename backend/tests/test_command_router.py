from app.providers.openrouter import PlannerResult
from app.router.ai_planner import AIPlanner
from app.router.command_router import CommandRouter
from app.core.config import get_settings


def test_welcome_home_command_routes_to_scenario() -> None:
    result = CommandRouter(get_settings()).handle(
        "Джарвис, я вернулся",
        context={"dry_run": True},
    )
    assert result["status"] == "completed"
    assert result["route"] == "scenario"
    assert result["route_detail"] == "scenario:welcome_home"
    assert "С возвращением" in result["response_text"]
    assert result["actions"][0]["type"] == "play_music_search"
    assert result["actions"][0]["status"] == "playback_attempted"
    assert result["actions"][0]["playback_attempted"] is True


def test_news_command_routes_to_scenario() -> None:
    result = CommandRouter(get_settings()).handle("Есть новости?", context={"dry_run": True})
    assert result["route"] == "scenario"
    assert result["route_detail"] == "scenario:news"
    assert result["status"] == "completed"


def test_workspace_command_routes_to_scenario() -> None:
    result = CommandRouter(get_settings()).handle(
        "Настрой мою среду работы",
        context={"dry_run": True},
    )
    assert result["route"] == "scenario"
    assert result["route_detail"] == "scenario:workspace"
    assert result["status"] == "completed"


def test_open_telegram_local_command() -> None:
    result = CommandRouter(get_settings()).handle(
        "Джарвис, открой Telegram",
        context={"dry_run": True},
    )
    assert result["route"] == "local_command"
    assert result["status"] == "completed"
    assert result["actions"][0]["target"] == "telegram"


def test_music_command_attempts_playback() -> None:
    result = CommandRouter(get_settings()).handle(
        "Джарвис, открой музыку",
        context={"dry_run": True},
    )
    assert result["route"] == "scenario"
    assert result["route_detail"] == "scenario:music"
    assert result["actions"][0]["type"] == "play_music_search"
    assert result["actions"][0]["playback_attempted"] is True
    assert [action["target"] for action in result["actions"][0]["actions"][1:]] == [
        "enter",
        "media_play_pause",
    ]


def test_unknown_command_uses_ai_planner(monkeypatch) -> None:
    def fake_plan(self: AIPlanner, text: str) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Идея: сайт для личных сценариев JARVIS.",
            actions=[],
            provider="test",
        )

    monkeypatch.setattr(AIPlanner, "plan", fake_plan)
    result = CommandRouter(get_settings()).handle(
        "Джарвис, придумай идею для сайта",
        context={"dry_run": True},
    )
    assert result["route"] == "ai_fallback"
    assert "Идея" in result["response_text"]
