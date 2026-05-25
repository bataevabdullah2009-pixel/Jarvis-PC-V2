from __future__ import annotations

import os

import uvicorn


def main() -> None:
    app_path = "app.main:app"
    host = os.getenv("JARVIS_BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("JARVIS_BACKEND_PORT", "18000"))
    log_level = os.getenv("JARVIS_BACKEND_LOG_LEVEL", "info")
    uvicorn.run(app_path, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
