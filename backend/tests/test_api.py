from app.main import app
from app.providers.openrouter import PlannerResult
from app.router.ai_planner import AIPlanner
from fastapi.testclient import TestClient


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"


def test_build_info_has_license_disabled() -> None:
    response = client.get("/runtime/build-info")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["app"] == "JARVIS PC V2"
    assert data["license_enabled"] is False


def test_assistant_command_contract_welcome_home() -> None:
    response = client.post(
        "/assistant/command",
        json={
            "text": "Джарвис, я вернулся",
            "source": "test",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["route"] == "scenario"
    assert body["data"]["route_detail"] == "scenario:welcome_home"
    assert body["data"]["actions"][0]["type"] == "play_music_search"


def test_scenario_music_contract() -> None:
    response = client.post(
        "/scenarios/music",
        json={"context": {"dry_run": True, "query": "Back in Black"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["actions"][0]["playback_attempted"] is True


def test_commands_contract() -> None:
    response = client.get("/commands")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "commands" in body["data"]


def test_diagnostics_contract() -> None:
    response = client.get("/diagnostics/full-test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["checks"]["backend"] == "ok"


def test_system_monitor_contract() -> None:
    response = client.get("/diagnostics/system-monitor")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "cpu_count" in body["data"]
    assert "disk_free_gb" in body["data"]


def test_assistant_command_contract_ai(monkeypatch) -> None:
    def fake_plan(self: AIPlanner, text: str) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Идея: локальная панель для быстрых AI-команд.",
            actions=[],
            provider="test",
        )

    monkeypatch.setattr(AIPlanner, "plan", fake_plan)
    response = client.post(
        "/assistant/command",
        json={
            "text": "Джарвис, придумай идею для сайта",
            "source": "test",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route"] == "ai_fallback"
    assert "Идея" in data["response_text"]
