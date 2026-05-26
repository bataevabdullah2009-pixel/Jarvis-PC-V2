# Optional local voice engines

Jarvis PC V2 can keep using Fish Audio while you prepare local engines separately.
The launcher does not install heavy voice models automatically.

## Piper

Piper is the lightest optional local TTS path.

1. Run `tools/voice_engines/install_piper.ps1`.
2. Download a Piper voice `.onnx` file and the matching `.onnx.json` config.
3. Put both files into `models/piper`.
4. Configure `.env`:

```env
JARVIS_PIPER_ENABLED=true
JARVIS_PIPER_MODEL_PATH=models/piper/ru_RU.onnx
JARVIS_PIPER_CONFIG_PATH=models/piper/ru_RU.onnx.json
JARVIS_PIPER_EXE_PATH=C:\path\to\piper.exe
JARVIS_PIPER_SPEAKER_ID=
```

Then open the Jarvis voice profile UI and select `piper_local`.
If the model, config, or executable is missing, Jarvis returns a structured diagnostic instead of crashing.

## GPT-SoVITS

GPT-SoVITS is a heavy external engine. It is not installed into the main backend environment.

1. Run `tools/voice_engines/install_gpt_sovits.ps1` to print the helper instructions.
2. Clone the official project yourself:

```powershell
git clone https://github.com/RVC-Boss/GPT-SoVITS.git external/GPT-SoVITS
```

3. Train or configure the voice according to the GPT-SoVITS documentation.
4. Start its local API server.
5. Configure `.env`:

```env
JARVIS_GPT_SOVITS_ENABLED=true
JARVIS_GPT_SOVITS_API_URL=http://127.0.0.1:9880
JARVIS_GPT_SOVITS_REFER_WAV=C:\path\to\reference.wav
JARVIS_GPT_SOVITS_PROMPT_TEXT=reference text
JARVIS_GPT_SOVITS_PROMPT_LANG=ru
JARVIS_GPT_SOVITS_TEXT_LANG=ru
```

Then select `gpt_sovits_local` in a voice profile.
If the server is not running, Jarvis reports `gpt_sovits_api_unreachable`.

## XTTS v2

XTTS is prepared as an external API placeholder.
Jarvis expects a local API at:

```env
JARVIS_XTTS_ENABLED=false
JARVIS_XTTS_API_URL=http://127.0.0.1:8020
```

Enable it only after you start your own XTTS server.

## RVC

RVC is prepared as a converter placeholder.
Jarvis expects a local API at:

```env
JARVIS_RVC_ENABLED=false
JARVIS_RVC_API_URL=http://127.0.0.1:7897
```

Enable it only after you run your own RVC service.

## Diagnostics

Use:

```text
GET http://127.0.0.1:18000/debug/local-voice-status
```

The response includes `fish_audio`, `piper_local`, `gpt_sovits_local`, `xtts_local`, `rvc_converter`, and `text_only`.
