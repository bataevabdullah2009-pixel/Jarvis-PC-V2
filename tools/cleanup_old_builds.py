from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "_archive" / "old_builds"
REPORT_TXT = ROOT / "tools" / "cleanup_report.txt"
REPORT_JSON = ROOT / "tools" / "cleanup_report.json"

PROTECTED_ROOT_NAMES = {
    "app",
    "src",
    "electron",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "config",
    "tools",
    "backend",
}

BUILD_DIR_NAMES = {
    "release",
    "dist",
    "dist_pc",
    "dist_release",
    "generated",
}

OLD_NAME_MARKERS = {
    "command center",
    "command-center",
    "hud",
    "old_build",
    "old-build",
    "installer",
}


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def is_protected(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return True
    parts = rel.parts
    if not parts:
        return True
    if parts[0] in PROTECTED_ROOT_NAMES:
        return True
    if len(parts) >= 2 and parts[0] == "frontend" and parts[1] in {"src", "electron", "package.json"}:
        return True
    if len(parts) >= 2 and parts[0] == "frontend" and parts[1] == "backend_package":
        return True
    if len(parts) >= 2 and parts[0] == "backend" and parts[1] in {"app", "config", "requirements.txt", "pyproject.toml"}:
        return True
    return False


def collect_candidates() -> tuple[list[Path], list[dict[str, str]]]:
    candidates: set[Path] = set()
    manual_review: list[dict[str, str]] = []

    for name in ["release", "dist", "dist_pc", "dist_release"]:
        path = ROOT / name
        if path.exists():
            candidates.add(path)

    generated = ROOT / "installer" / "generated"
    if generated.exists():
        candidates.add(generated)

    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        candidates.add(frontend_dist)

    for path in ROOT.rglob("*"):
        if "_archive" in path.parts or "node_modules" in path.parts or ".git" in path.parts:
            continue
        lowered = path.name.lower()
        if path.is_dir() and path.name in BUILD_DIR_NAMES and not is_protected(path):
            candidates.add(path)
        if path.is_file() and path.suffix.lower() in {".exe", ".msi", ".zip", ".7z", ".rar"}:
            if "jarvis" in lowered or "command" in lowered or "hud" in lowered:
                if is_protected(path):
                    manual_review.append({"path": relative(path), "reason": "protected path"})
                else:
                    candidates.add(path)
        if path.is_dir() and any(marker in lowered for marker in OLD_NAME_MARKERS):
            if is_protected(path):
                manual_review.append({"path": relative(path), "reason": "protected path"})
            else:
                candidates.add(path)

    ordered = sorted(candidates, key=lambda item: len(item.parts))
    filtered: list[Path] = []
    for candidate in ordered:
        if is_protected(candidate):
            manual_review.append({"path": relative(candidate), "reason": "protected path"})
            continue
        if any(parent in candidate.parents for parent in filtered):
            continue
        filtered.append(candidate)

    return filtered, manual_review


def archive_path(candidate: Path, archive_dir: Path) -> Path:
    target = archive_dir / relative(candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def main() -> int:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    archive_dir = ARCHIVE_ROOT / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)

    found, manual_review = collect_candidates()
    archived: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for candidate in found:
        target = archive_path(candidate, archive_dir)
        try:
            shutil.move(str(candidate), str(target))
            archived.append({"from": relative(candidate), "to": relative(target)})
        except Exception as exc:
            skipped.append({"path": relative(candidate), "reason": exc.__class__.__name__})

    report = {
        "archive_dir": relative(archive_dir),
        "found": [relative(path) for path in found],
        "archived": archived,
        "skipped": skipped,
        "manual_review": manual_review,
    }

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"Archive directory: {report['archive_dir']}",
        "",
        "Found:",
        *[f"- {item}" for item in report["found"]],
        "",
        "Archived:",
        *[f"- {item['from']} -> {item['to']}" for item in archived],
        "",
        "Skipped:",
        *[f"- {item['path']}: {item['reason']}" for item in skipped],
        "",
        "Manual review:",
        *[f"- {item['path']}: {item['reason']}" for item in manual_review],
    ]
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Archived {len(archived)} item(s) to {archive_dir}")
    print(f"Reports: {REPORT_TXT} and {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
