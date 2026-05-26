#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "node_modules",
    "_archive",
    "build",
    "dist",
    "release",
    "app_current",
    "data",
    ".venv",
    "venv",
    "__pycache__",
}
TEXT_EXTENSIONS = {
    ".bat",
    ".ps1",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".md",
    ".css",
    ".html",
}
CRLF_EXTENSIONS = {".bat", ".ps1"}
LF_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".css", ".html"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_bytes(path: Path, errors: list[str]) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        errors.append(f"Read: {rel(path)} failed: {exc}")
        return b""


def non_empty_line_count(path: Path, errors: list[str]) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        errors.append(f"Read: {rel(path)} failed: {exc}")
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def check_line_endings(path: Path, content: bytes, errors: list[str]) -> None:
    if not content:
        return

    path_rel = rel(path)
    ext = path.suffix.lower()
    lf_count = content.count(b"\n")
    cr_count = content.count(b"\r")
    crlf_count = content.count(b"\r\n")
    isolated_cr = content.replace(b"\r\n", b"").count(b"\r")
    first_line = content.splitlines()[0] if content.splitlines() else b""

    if lf_count == 0:
        errors.append(f"Format: {path_rel} has LF count == 0")

    if isolated_cr:
        errors.append(f"Format: {path_rel} CR-only line endings detected")

    if len(first_line) > 2000:
        errors.append(
            f"Format: {path_rel} first line is longer than 2000 bytes ({len(first_line)} bytes)"
        )

    if ext in CRLF_EXTENSIONS and lf_count != crlf_count:
        errors.append(f"Format: {path_rel} must use CRLF line endings")

    if ext in LF_EXTENSIONS and cr_count != 0:
        errors.append(f"Format: {path_rel} must use LF line endings")


def check_python_compile(path: Path, errors: list[str]) -> None:
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        errors.append(f"Python: {rel(path)} fails compilation: {exc.msg}")
    except Exception as exc:  # pragma: no cover - defensive guard
        errors.append(f"Python: {rel(path)} fails to compile: {exc}")


def check_batch(path: Path, errors: list[str]) -> None:
    count = non_empty_line_count(path, errors)
    if count < 4:
        errors.append(f"Batch: {rel(path)} must contain at least 4 non-empty lines, got {count}")


def check_powershell(path: Path, errors: list[str]) -> None:
    count = non_empty_line_count(path, errors)
    if rel(path) == "tools/start_jarvis.ps1" and count < 80:
        errors.append(
            f"PowerShell: tools/start_jarvis.ps1 must contain at least 80 non-empty lines, got {count}"
        )


def check_required_file_lengths(errors: list[str]) -> None:
    required = {
        "tools/check_source_format.py": 120,
        "tools/start_jarvis.ps1": 80,
        ".env.example": 60,
        "README.md": 80,
        "backend/run_backend.py": 10,
        "backend/app/main.py": 300,
        "backend/app/core/config.py": 150,
        "frontend/src/api/client.ts": 150,
        "frontend/src/screens/MinimalUI.tsx": 300,
    }
    for relative, minimum in required.items():
        path = ROOT / relative
        if not path.exists():
            errors.append(f"Required: {relative} is missing")
            continue
        count = non_empty_line_count(path, errors)
        if count < minimum:
            errors.append(
                f"Required: {relative} must contain at least {minimum} non-empty lines, got {count}"
            )


def check_gitattributes(errors: list[str]) -> None:
    path = ROOT / ".gitattributes"
    if not path.exists():
        errors.append(".gitattributes: file is missing")
        return

    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as exc:
        errors.append(f".gitattributes: failed to read: {exc}")
        return

    if "* text=auto" not in lines:
        errors.append(".gitattributes: missing '* text=auto'")


def iter_files() -> list[Path]:
    paths: list[Path] = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in EXCLUDE_DIRS]
        root_path = Path(root)
        for filename in files:
            paths.append(root_path / filename)
    return paths


def main() -> int:
    print(f"Scanning codebase for formatting issues starting from root: {ROOT}")
    errors: list[str] = []

    check_gitattributes(errors)

    for path in iter_files():
        ext = path.suffix.lower()
        if ext not in TEXT_EXTENSIONS:
            continue

        content = read_bytes(path, errors)
        check_line_endings(path, content, errors)

        if ext == ".py":
            check_python_compile(path, errors)
        elif ext == ".bat":
            check_batch(path, errors)
        elif ext == ".ps1":
            check_powershell(path, errors)

    check_required_file_lengths(errors)

    if errors:
        print("\n[!] FORMATTING AND COMPILATION ERRORS DETECTED:")
        for error in errors:
            print(f"  - {error}")
        print(f"\nTotal violations: {len(errors)}")
        return 1

    print("\n[+] SUCCESS: No formatting or compilation errors detected in the codebase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
