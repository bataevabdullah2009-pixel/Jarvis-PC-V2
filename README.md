# JARVIS PC V2 Minimal Assistant

## Dev запуск

1. Backend: `cd backend && python run_backend.py`
2. Frontend: `cd frontend && npm.cmd run dev`
3. Открыть UI: `http://127.0.0.1:5173`

## Сборка portable

```powershell
cd frontend
npm.cmd run package:portable
```

## Как очистить старые сборки

Скрипт не удаляет файлы. Он переносит старые сборки, установщики и legacy-артефакты в `_archive/old_builds/YYYY-MM-DD_HH-MM/`.

```powershell
python tools\cleanup_old_builds.py
```

После запуска проверьте:

- `tools/cleanup_report.txt`
- `tools/cleanup_report.json`

Скрипт не трогает backend source, `app/`, `src/`, `electron/`, `package.json`, `requirements.txt`, `pyproject.toml`, `config/` и `tools/`.
