from app.router.intent_detector import match_open_app, match_scenario, normalize_text


def test_normalize_text_strips_wake_word_and_punctuation() -> None:
    assert normalize_text("Джарвис, я вернулся!") == "я вернулся"


def test_match_required_scenarios() -> None:
    assert match_scenario(normalize_text("Джарвис, я вернулся")).name == "welcome_home"
    assert match_scenario(normalize_text("Есть новости?")).name == "news"
    assert match_scenario(normalize_text("Настрой мою среду работы")).name == "workspace"
    assert match_scenario(normalize_text("Открой музыку")).name == "music"


def test_match_open_app() -> None:
    assert match_open_app(normalize_text("Джарвис, открой Telegram")) == "telegram"
