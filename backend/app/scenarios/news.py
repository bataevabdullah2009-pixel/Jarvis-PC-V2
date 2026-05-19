from __future__ import annotations

from app.core.config import Settings
from app.news.feed import fetch_headlines
from app.pc.browser import open_url


TRIGGERS = {
    "есть новости",
    "что нового",
    "открой новости",
    "прочитай новости",
    "джарвис новости",
}


def run(settings: Settings, *, dry_run: bool = False, limit: int = 5) -> dict:
    actions = [open_url(settings.news_url, dry_run=dry_run)]
    headlines = []
    feed_error = None

    if not dry_run:
        headlines, feed_error = fetch_headlines(settings.news_rss_url, limit=limit)

    if headlines:
        titles = "; ".join(item["title"] for item in headlines[:limit])
        response_text = f"Сэр, вот главные новости: {titles}"
        source = "rss"
    elif dry_run:
        response_text = "Сэр, я открыл новости. В dry run RSS не запрашиваю."
        source = "dry_run"
    else:
        response_text = "Сэр, я открыл новости. Сводка сейчас недоступна."
        source = "browser_fallback"

    return {
        "scenario": "news",
        "status": "completed",
        "response_text": response_text,
        "actions": actions,
        "headlines": headlines,
        "source": source,
        "warnings": [feed_error] if feed_error else [],
    }
