from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "backend" / "models"
MODEL_NAME = "vosk-model-small-ru-0.22"
MODEL_ZIP = MODELS_DIR / f"{MODEL_NAME}.zip"
MODEL_DIR = MODELS_DIR / MODEL_NAME
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


def main() -> int:
    if MODEL_DIR.exists():
        print(f"Model already exists: {MODEL_DIR}")
        return 0

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, MODEL_ZIP)

    temp_dir = MODELS_DIR / "_extracting"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()

    print("Extracting model")
    with zipfile.ZipFile(MODEL_ZIP) as archive:
        archive.extractall(temp_dir)

    extracted = temp_dir / MODEL_NAME
    if not extracted.exists():
        raise RuntimeError(f"Unexpected archive layout: {MODEL_ZIP}")

    shutil.move(str(extracted), str(MODEL_DIR))
    shutil.rmtree(temp_dir)
    MODEL_ZIP.unlink(missing_ok=True)
    print(f"Model installed: {MODEL_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

