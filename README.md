# JARVIS PC V2 Minimal Assistant

## Главный запуск

Запускайте JARVIS только из корня проекта:

```bat
START_JARVIS.bat
```

Это единственный нормальный launcher для обычной работы.

## Runtime Port

JARVIS backend теперь использует постоянный порт:

```text
18000
```

Backend URL:

```text
http://127.0.0.1:18000
```

Frontend получает адрес backend через:

```text
VITE_JARVIS_API_BASE=http://127.0.0.1:18000
```

Если другой backend занимает порт `8000`, это больше не мешает JARVIS. Порт `8000` не является runtime-портом JARVIS.

## Что Делает START_JARVIS

`START_JARVIS.bat` вызывает `tools\start_jarvis.ps1`.

Launcher:

- определяет root проекта;
- задает `JARVIS_BACKEND_PORT=18000`, если переменная не задана;
- задает `VITE_JARVIS_API_BASE` для frontend;
- останавливает только старые JARVIS процессы;
- освобождает только выбранный JARVIS port;
- игнорирует `TIME_WAIT` и PID 0;
- не убивает чужие процессы без ручного вмешательства;
- проверяет `backend\.env`;
- проверяет backend dependencies;
- проверяет frontend dependencies;
- запускает FastAPI backend;
- ждет `/health`;
- запускает Vite frontend dev server;
- ждет `http://127.0.0.1:5173`;
- запускает Electron;
- при закрытии Electron останавливает backend и frontend.

## Legacy Launchers

Эти файлы оставлены только для совместимости:

- `RUN_DEV_FRESH.bat` перенаправляет на `START_JARVIS.bat`.
- `UPDATE_AND_LAUNCH_APP.bat` предназначен для update/build сценария.

Для обычного запуска legacy launchers не используйте.

## Diagnostics

Проверка backend:

```powershell
curl.exe http://127.0.0.1:18000/health
curl.exe http://127.0.0.1:18000/runtime/process-info
curl.exe http://127.0.0.1:18000/debug/env-status
curl.exe http://127.0.0.1:18000/debug/network-status
curl.exe http://127.0.0.1:18000/debug/voice-provider-status
```

## Smoke Runtime

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_runtime.ps1
```

Smoke проверяет backend startup, diagnostics endpoints, listener disabled state и assistant ask без зависимости от порта `8000`.

## Source Format Guard

Перед коммитом:

```powershell
python tools\check_source_format.py
```

Guard проверяет переносы строк, минимальное число строк у launcher-файлов, длинную первую строку и компиляцию Python-файлов.
