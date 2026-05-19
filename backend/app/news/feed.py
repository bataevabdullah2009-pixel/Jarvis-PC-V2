from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


def fetch_headlines(feed_url: str, *, limit: int = 5, timeout: int = 5) -> tuple[list[dict[str, Any]], str | None]:
    try:
        with urllib.request.urlopen(feed_url, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        return [], exc.__class__.__name__

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return [], exc.__class__.__name__

    headlines: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            headlines.append({"title": title, "url": link})
        if len(headlines) >= limit:
            break

    return headlines, None

