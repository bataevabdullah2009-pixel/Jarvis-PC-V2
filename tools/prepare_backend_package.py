from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PACKAGE = ROOT / "frontend" / "backend_package"
EXCLUDES = {
    "__pycache__",
    ".pytest_cache",
    "tests",
    "logs",
}


def ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in EXCLUDES}
    ignored.update(name for name in names if name.endswith(".pyc"))
    return ignored


def main() -> int:
    required = [
        BACKEND / "app",
        BACKEND / "run_backend.py",
        BACKEND / "requirements.txt",
        BACKEND / "pyproject.toml",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"Backend package cannot be created. Missing: {', '.join(missing)}")

    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    PACKAGE.mkdir(parents=True)

    for name in ["app", "config", "models"]:
        source = BACKEND / name
        if source.exists():
            shutil.copytree(source, PACKAGE / name, ignore=ignore)

    for name in ["run_backend.py", "requirements.txt", "pyproject.toml"]:
        source = BACKEND / name
        if source.exists():
            shutil.copy2(source, PACKAGE / name)

    if not (PACKAGE / "run_backend.py").exists():
        raise SystemExit("Backend package is invalid: run_backend.py was not copied.")
    if not (PACKAGE / "app" / "main.py").exists():
        raise SystemExit("Backend package is invalid: app/main.py was not copied.")

    print(f"Backend package prepared: {PACKAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
