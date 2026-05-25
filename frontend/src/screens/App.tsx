import { useEffect, useState } from "react";
import {
  api,
  AppStatusData,
  BuildInfoData,
  CommandDefinition,
  CommandResult,
  DebugEnvStatus,
  AIProviderStatusData,
  DiagnosticsData,
  FullHealthData,
  LicenseStatusData,
  MicrophoneTestData,
  ProviderTestResult,
  SettingsData,
  TTSStatusData,
  VoiceProviderStatusData,
  VoiceDependencyData,
  VoiceDevice
} from "../api/client";
import { MinimalUI } from "./MinimalUI";
import { playSound } from "../services/soundManager";

export type Screen = "home" | "commands" | "scenarios" | "myCommands" | "voices" | "environment" | "settings" | "diagnostics";
export type AssistantStatus = "ready" | "listening" | "working" | "done" | "warning" | "error";

export type CommandHistoryItem = {
  id: string;
  userText: string;
  assistantText: string;
  route: string;
  status: string;
  time: string;
};

export type AppState = {
  screen: Screen;
  assistantStatus: AssistantStatus;
  statusText: string;
  health: FullHealthData | null;
  appStatus: AppStatusData | null;
  license: LicenseStatusData | null;
  voice: VoiceDependencyData | null;
  ttsStatus: TTSStatusData | null;
  settings: SettingsData | null;
  devices: VoiceDevice[];
  commands: CommandDefinition[];
  diagnostics: DiagnosticsData | null;
  debugEnv: DebugEnvStatus | null;
  aiProviderStatus: AIProviderStatusData | null;
  voiceProviderStatus: VoiceProviderStatusData | null;
  openrouterTest: ProviderTestResult | null;
  fishAudioTest: ProviderTestResult | null;
  aiFallbackTest: CommandResult | null;
  lastResult: CommandResult | null;
  lastMicrophoneTest: MicrophoneTestData | null;
  history: CommandHistoryItem[];
  lastError: string | null;
  debugMode: boolean;
  buildInfo: BuildInfoData | null;
  listenerStatus: any | null;
};

const DEFAULT_ASSISTANT_TEXT = "Команда выполнена.";

function stripMojibake(text: string | null | undefined, fallback = ""): string {
  if (!text) return fallback;
  if (/[\u00d0\u00c2]|\u0420\u045f|\u0420\u0405|\u0420\u00a0|\u0432\u0459|\u043f\u0451/.test(text)) {
    return fallback || "Backend вернул поврежденную строку кодировки.";
  }
  return text;
}

function normalErrorMessage(error: unknown, fallback = "Backend недоступен. Проверьте, запущен ли python run_backend.py. Откройте /debug/startup или /health."): string {
  const raw =
    typeof error === "string"
      ? error
      : error instanceof Error
        ? error.message
        : typeof error === "object" && error && "message" in error
          ? String((error as { message?: unknown }).message ?? "")
          : "";
  const text = raw.trim();
  if (!text || /failed to fetch/i.test(text) || /networkerror/i.test(text) || /load failed/i.test(text)) {
    return fallback;
  }
  return text;
}

function resultText(result: CommandResult | null | undefined): string {
  return (result?.text || result?.response_text || "").trim() || DEFAULT_ASSISTANT_TEXT;
}

function isCommandSuccess(data: CommandResult): boolean {
  return Boolean(data.executed) || data.status === "completed" || data.status === "warning" || data.status === "success_with_warning";
}

function isTtsQueued(data: CommandResult): boolean {
  return data.tts?.status === "queued" || Boolean(data.tts?.async || data.tts?.pending_audio);
}

function isCommandWarning(data: CommandResult): boolean {
  return (
    data.status === "warning" ||
    data.status === "success_with_warning" ||
    Boolean(data.tts && !isTtsQueued(data) && data.tts.ok === false)
  );
}

export function App() {
  const [state, setState] = useState<AppState>({
    screen: "home",
    assistantStatus: "ready",
    statusText: "Готов",
    health: null,
    appStatus: null,
    license: null,
    voice: null,
    ttsStatus: null,
    settings: null,
    devices: [],
    commands: [],
    diagnostics: null,
    debugEnv: null,
    aiProviderStatus: null,
    voiceProviderStatus: null,
    openrouterTest: null,
    fishAudioTest: null,
    aiFallbackTest: null,
    lastResult: null,
    lastMicrophoneTest: null,
    history: [],
    lastError: null,
    debugMode: false,
    buildInfo: null,
    listenerStatus: null
  });

  const setScreen = (screen: Screen) => {
    setState((current) => ({ ...current, screen }));
  };

  const refreshStatus = async () => {
    const [health, appStatus, license, voice, ttsStatus, settings, devices, commands, debugEnv, aiProviderStatus, voiceProviderStatus, buildInfo, listenerStatus] = await Promise.all([
      api.fullHealth(),
      api.appStatus(),
      api.licenseStatus(),
      api.voiceDependencies(),
      api.ttsStatus(),
      api.settings(),
      api.voiceDevices(),
      api.commands(),
      api.debugEnvStatus(),
      api.aiProviderStatus(),
      api.voiceProviderStatus(),
      api.buildInfo(),
      api.listenerStatus()
    ]);
    const isBackendAlive = Boolean(health.ok);
    setState((current) => ({
      ...current,
      health: isBackendAlive ? health.data : null,
      appStatus: appStatus.ok ? appStatus.data : current.appStatus,
      license: license.ok ? license.data : current.license,
      voice: voice.ok ? voice.data : current.voice,
      ttsStatus: ttsStatus.ok ? ttsStatus.data : current.ttsStatus,
      settings: settings.ok ? settings.data : current.settings,
      debugMode: settings.ok ? Boolean(settings.data?.debug_mode) : current.debugMode,
      devices: devices.ok ? devices.data?.input_devices ?? [] : current.devices,
      commands: commands.ok ? commands.data?.commands ?? [] : current.commands,
      debugEnv: debugEnv.ok ? debugEnv.data : current.debugEnv,
      aiProviderStatus: aiProviderStatus.ok ? aiProviderStatus.data : current.aiProviderStatus,
      voiceProviderStatus: voiceProviderStatus.ok ? voiceProviderStatus.data : current.voiceProviderStatus,
      buildInfo: buildInfo.ok ? buildInfo.data : current.buildInfo,
      listenerStatus: isBackendAlive && listenerStatus.ok ? listenerStatus.data : null,
      assistantStatus: isBackendAlive ? current.assistantStatus : "error",
      statusText: isBackendAlive ? current.statusText : "Ошибка",
      lastError: isBackendAlive ? current.lastError : "Backend не запущен. Запустите START_JARVIS.bat"
    }));
  };

  useEffect(() => {
    playSound("startup");
    refreshStatus();
    const timer = window.setInterval(refreshStatus, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const applyCommandResult = (userText: string, data: CommandResult) => {
    const assistantText = stripMojibake(resultText(data), DEFAULT_ASSISTANT_TEXT);
    const ttsProvider = data.tts?.provider ?? "none";
    const ttsOk = data.tts?.ok !== false;
    let ttsUnavailable: string | null = null;
    
    if (ttsProvider === "none") {
      ttsUnavailable = "Backend вернул некорректный TTS provider none";
    } else if (!ttsOk || ttsProvider === "text_only") {
      const ttsErr = stripMojibake(data.tts?.error, data.tts?.status || "unknown");
      const ttsFix = stripMojibake(
        data.tts?.fix || (data.tts?.details?.fix as string | undefined),
        state.voiceProviderStatus?.fish_key_present && state.voiceProviderStatus?.fish_voice_id_present
          ? "Проверьте доступность Fish Audio API и лимиты."
          : "Добавьте JARVIS_FISH_AUDIO_API_KEY и JARVIS_FISH_AUDIO_VOICE_ID в backend/.env"
      );
      const errorType = data.tts?.status || (data.tts as any)?.error_type || state.voiceProviderStatus?.last_error_type || "unknown";
      ttsUnavailable = `Голос недоступен (Provider: ${ttsProvider}). Тип: ${errorType}. Ошибка: ${ttsErr}. Решение: ${ttsFix}`;
    } else if (data.tts?.fallback_used) {
      const ttsFix = data.tts?.fix || "Проверьте ключи Fish Audio в .env.";
      ttsUnavailable = `Использован резервный голос (${ttsProvider}), основной недоступен. Решение: ${ttsFix}`;
    }
    const historyItem: CommandHistoryItem = {
      id: data.command_id,
      userText,
      assistantText,
      route: data.route,
      status: data.status,
      time: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    };

    const success = isCommandSuccess(data);
    const warning = success && isCommandWarning(data);
    playSound(success ? (warning ? "notification" : "success") : "error");

    setState((current) => ({
      ...current,
      assistantStatus: success ? (warning ? "warning" : "done") : data.handled === false ? "warning" : "error",
      statusText: success ? (warning ? "Выполнено с предупреждением" : "Выполнено") : data.handled === false ? "Не понял" : "Ошибка",
      lastResult: { ...data, text: assistantText, response_text: assistantText },
      history: [historyItem, ...current.history].slice(0, 24),
      lastError: success ? ttsUnavailable : assistantText
    }));
  };

  const sendCommand = async (text: string) => {
    const command = text.trim();
    if (!command) {
      return;
    }

    playSound("command_start");
    setState((current) => ({ ...current, assistantStatus: "working", statusText: "Выполняю", lastError: null }));

    const response = await api.sendCommand(command);

    if (!response.ok || !response.data) {
      setState((current) => ({
        ...current,
        assistantStatus: "error",
        statusText: "Ошибка",
        lastError: normalErrorMessage(response.error, "Backend недоступен")
      }));
      playSound("error");
      return;
    }

    applyCommandResult(command, response.data);
  };

  const runScenario = async (name: "welcome-home" | "news" | "workspace" | "music") => {
    const commandByScenario = {
      "welcome-home": "Джарвис, я вернулся",
      news: "Есть новости?",
      workspace: "Настрой мою среду работы",
      music: "Back in Black"
    };
    await sendCommand(commandByScenario[name]);
  };

  const recordVoice = async (deviceId?: string) => {
    const devId = deviceId ?? localStorage.getItem("selected_device_id") ?? "default";
    playSound("listening");
    setState((current) => ({
      ...current,
      assistantStatus: "listening",
      statusText: "Слушаю 5 секунд...",
      lastError: null
    }));
    const response = await api.recordCommand(devId, 5);
    if (!response.ok || !response.data) {
      setState((current) => ({
        ...current,
        assistantStatus: "error",
        statusText: "Ошибка",
        lastError: normalErrorMessage(response.error, "Голосовой модуль недоступен")
      }));
      playSound("error");
      return;
    }

    const data = response.data;
    const finalStatus = data.final_status;

    if (finalStatus === "no_audio") {
      setState((current) => ({
        ...current,
        assistantStatus: "error",
        statusText: "Микрофон не получает звук",
        lastError: data.stt?.fix || "Микрофон не получает звук. Проверьте громкость и подключение."
      }));
      playSound("error");
      return;
    }

    if (finalStatus === "stt_not_configured") {
      setState((current) => ({
        ...current,
        assistantStatus: "error",
        statusText: "STT/Vosk не настроен",
        lastError: data.stt?.fix || "Микрофон слышит, но STT не настроен."
      }));
      playSound("error");
      return;
    }

    if (finalStatus === "empty_transcript") {
      setState((current) => ({
        ...current,
        assistantStatus: "warning",
        statusText: "Речь не распознана",
        lastError: data.stt?.fix || "Речь не распознана. Говорите громче и чётче."
      }));
      playSound("error");
      return;
    }

    if (finalStatus === "record_error") {
      setState((current) => ({
        ...current,
        assistantStatus: "error",
        statusText: "Голосовой модуль недоступен",
        lastError: data.stt?.fix || data.stt?.error_type || "Ошибка при записи звука."
      }));
      playSound("error");
      return;
    }

    const transcript = data.stt?.transcript?.trim();
    const assistantResult = data.assistant_result;

    if (finalStatus === "sent_to_assistant" && transcript && assistantResult) {
      playSound("command_received");
      applyCommandResult(transcript, assistantResult);
      return;
    }

    if (transcript && assistantResult) {
      playSound("command_received");
      applyCommandResult(transcript, assistantResult);
      return;
    }

    if (finalStatus === "recorded" && transcript) {
      setState((current) => ({
        ...current,
        assistantStatus: "done",
        statusText: "Записано",
        lastResult: {
          ...current.lastResult,
          response_text: `Распознано: "${transcript}"`
        } as any
      }));
      playSound("success");
      return;
    }

    if (transcript) {
      playSound("command_received");
      await sendCommand(transcript);
      return;
    }

    setState((current) => ({
      ...current,
      assistantStatus: "error",
      statusText: "Ошибка",
      lastError: "STT сработал, но текст пустой"
    }));
    playSound("error");
  };

  const testMicrophone = async (deviceId?: string) => {
    const devId = deviceId ?? localStorage.getItem("selected_device_id") ?? "default";
    playSound("listening");
    setState((current) => ({ ...current, assistantStatus: "listening", statusText: "Слушаю 3 секунды...", lastError: null }));
    const response = await api.testMicrophone(devId);
    if (!response.ok || !response.data) {
      setState((current) => ({
        ...current,
        assistantStatus: "error",
        statusText: "Ошибка",
        lastError: `${normalErrorMessage(response.error, "Голосовой модуль недоступен")} Установите: .venv\\Scripts\\python.exe -m pip install -r requirements.txt`
      }));
      playSound("error");
      return;
    }

    const data = response.data;
    setState((current) => ({
      ...current,
      assistantStatus: data.heard_signal ? "ready" : "error",
      statusText: data.heard_signal ? "Готов" : "Ошибка",
      lastMicrophoneTest: data,
      lastError: data.heard_signal ? null : `Сигнал слишком тихий. RMS ${data.rms.toFixed(5)}. Проверьте выбранный микрофон.`
    }));
    playSound(data.heard_signal ? "success" : "error");
  };

  const testVoice = async () => {
    playSound("command_start");
    setState((current) => ({ ...current, assistantStatus: "working", statusText: "Выполняю", lastError: null }));
    const response = await api.say("Голосовой модуль работает, сэр.");
    const provider = response.data?.provider ?? "text_only";
    const spoken = Boolean(response.data?.spoken);
    const played = Boolean(response.data?.played);
    
    let assistantText = "Голосовой модуль работает, сэр.";
    let errorMsg: string | null = null;
    
    if (response.ok && (spoken || played) && provider !== "text_only") {
      assistantText = "Голосовой модуль работает, сэр.";
    } else {
      const err = response.data?.error || response.error?.message || "Неизвестная ошибка";
      const fix = response.data?.fix || (response.error as any)?.details?.fix || "Проверьте настройки в .env.";
      assistantText = "Голосовой модуль недоступен, ответ показан текстом.";
      errorMsg = `Голос не воспроизведён. Provider: ${provider}. Причина: ${err}. Решение: ${fix}`;
    }
    
    setState((current) => ({
      ...current,
      assistantStatus: "ready",
      statusText: "Готов",
      history: [
        {
          id: `voice_${Date.now()}`,
          userText: "Проверить голос Джарвиса",
          assistantText,
          route: "voice:say",
          status: response.ok && provider !== "text_only" ? "completed" : "text_only",
          time: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
        },
        ...current.history
      ].slice(0, 24),
      lastError: errorMsg
    }));
    playSound(response.ok && provider !== "text_only" ? "success" : "error");
    await refreshStatus();
  };

  const testOpenRouter = async () => {
    const response = await api.testOpenRouter();
    setState((current) => ({
      ...current,
      openrouterTest: response.data,
      lastError: response.data && !response.data.ok ? response.data.error_message ?? response.data.fix ?? "OpenRouter test failed" : null
    }));
  };

  const testFishAudio = async () => {
    const response = await api.testFishAudio();
    setState((current) => ({
      ...current,
      fishAudioTest: response.data,
      lastError: response.data && !response.data.ok ? response.data.error_message ?? response.data.fix ?? "Fish Audio test failed" : null
    }));
  };

  const testAiFallback = async () => {
    const response = await api.testFullPipeline("Джарвис как дела?");
    if (response.data) {
      applyCommandResult("Джарвис как дела?", response.data);
    }
    setState((current) => ({
      ...current,
      aiFallbackTest: response.data,
      lastError: response.data && response.data.status !== "completed" ? resultText(response.data) : current.lastError
    }));
  };

  const loadDiagnostics = async () => {
    const [response, debugEnv] = await Promise.all([api.diagnostics(), api.debugEnvStatus()]);
    setState((current) => ({
      ...current,
      diagnostics: response.ok ? response.data : current.diagnostics,
      debugEnv: debugEnv.ok ? debugEnv.data : current.debugEnv,
      ttsStatus: response.ok ? response.data?.tts_status ?? current.ttsStatus : current.ttsStatus,
      lastError: response.ok ? current.lastError : normalErrorMessage(response.error, "Backend недоступен")
    }));
  };

  const patchSettings = async (patch: Partial<SettingsData>) => {
    const response = await api.patchSettings(patch);
    setState((current) => ({
      ...current,
      settings: response.ok ? response.data : current.settings,
      debugMode: response.ok ? Boolean(response.data?.debug_mode) : current.debugMode,
      lastError: response.ok ? current.lastError : normalErrorMessage(response.error, "Backend недоступен")
    }));
  };

  return (
    <MinimalUI
      state={state}
      onScreen={setScreen}
      onCommand={sendCommand}
      onScenario={runScenario}
      onRecordVoice={recordVoice}
      onTestMicrophone={testMicrophone}
      onTestVoice={testVoice}
      onTestOpenRouter={testOpenRouter}
      onTestFishAudio={testFishAudio}
      onTestAiFallback={testAiFallback}
      onRefresh={refreshStatus}
      onDiagnostics={loadDiagnostics}
      onPatchSettings={patchSettings}
    />
  );
}
