#!/usr/bin/env python3
from __future__ import annotations

import os
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


def normalize_file(path: Path) -> None:
    try:
        content = path.read_bytes()
    except OSError as exc:
        print(f"[!] Failed to read {path.relative_to(ROOT)}: {exc}")
        return

    ext = path.suffix.lower()
    
    # 1. Normalize line endings
    if ext in CRLF_EXTENSIONS:
        # Enforce CRLF
        normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n").replace(b"\n", b"\r\n")
    else:
        # Enforce LF
        normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    # 2. Check and wrap first line if too long
    lines = normalized.split(b"\n")
    if lines and len(lines[0]) > 500:
        first_line = lines[0].decode("utf-8", errors="ignore")
        print(f"[*] Wrapping long first line in {path.relative_to(ROOT)} ({len(lines[0])} bytes)")
        
        # Split first line at whitespace or comma close to 100 chars
        wrapped_chunks = []
        current_chunk = []
        current_len = 0
        for word in first_line.split(" "):
            if current_len + len(word) + 1 > 100:
                wrapped_chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_len = len(word)
            else:
                current_chunk.append(word)
                current_len += len(word) + 1
        if current_chunk:
            wrapped_chunks.append(" ".join(current_chunk))
        
        # Merge back
        comment_symbol = "#" if ext in {".py", ".pyw"} else "//" if ext in {".ts", ".tsx", ".js"} else "::"
        new_first_lines = [f"{comment_symbol} {chunk}".encode("utf-8") for chunk in wrapped_chunks]
        lines = new_first_lines + lines[1:]
        
        if ext in CRLF_EXTENSIONS:
            normalized = b"\r\n".join(lines)
        else:
            normalized = b"\n".join(lines)

    if normalized != content:
        try:
            path.write_bytes(normalized)
            print(f"[+] Normalized: {path.relative_to(ROOT)}")
        except OSError as exc:
            print(f"[!] Failed to write {path.relative_to(ROOT)}: {exc}")


def main() -> None:
    print(f"Traversing codebase and normalizing files starting from root: {ROOT}")
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in EXCLUDE_DIRS]
        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if path.suffix.lower() in TEXT_EXTENSIONS:
                normalize_file(path)


if __name__ == "__main__":
    main()
