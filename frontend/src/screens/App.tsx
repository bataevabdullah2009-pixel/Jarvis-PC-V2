import { useEffect, useState } from "react";
import {
  api,
  AppStatusData,
  CommandDefinition,
  CommandResult,
  DebugEnvStatus,
  DiagnosticsData,
  FullHealthData,
  LicenseStatusData,
  MicrophoneTestData,
  ProviderTestResult,
  SettingsData,
  TTSStatusData,
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
  openrouterTest: ProviderTestResult | null;
  fishAudioTest: ProviderTestResult | null;
  aiFallbackTest: CommandResult | null;
  lastResult: CommandResult | null;
  lastMicrophoneTest: MicrophoneTestData | null;
  history: CommandHistoryItem[];
  lastError: string | null;
  debugMode: boolean;
};

const DEFAULT_ASSISTANT_TEXT = "Команда выполнена.";

function normalErrorMessage(error: unknown, fallback = "Backend недоступен"): string {
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
    openrouterTest: null,
    fishAudioTest: null,
    aiFallbackTest: null,
    lastResult: null,
    lastMicrophoneTest: null,
    history: [],
    lastError: null,
    debugMode: false
  });

  const setScreen = (screen: Screen) => {
    setState((current) => ({ ...current, screen }));
  };

  const refreshStatus = async () => {
    const [health, appStatus, license, voice, ttsStatus, settings, devices, commands, debugEnv] = await Promise.all([
      api.fullHealth(),
      api.appStatus(),
      api.licenseStatus(),
      api.voiceDependencies(),
      api.ttsStatus(),
      api.settings(),
      api.voiceDevices(),
      api.commands(),
      api.debugEnvStatus()
    ]);

    setState((current) => ({
      ...current,
      health: health.ok ? health.data : current.health,
      appStatus: appStatus.ok ? appStatus.data : current.appStatus,
      license: license.ok ? license.data : current.license,
      voice: voice.ok ? voice.data : current.voice,
      ttsStatus: ttsStatus.ok ? ttsStatus.data : current.ttsStatus,
      settings: settings.ok ? settings.data : current.settings,
      debugMode: settings.ok ? Boolean(settings.data?.debug_mode) : current.debugMode,
      devices: devices.ok ? devices.data?.input_devices ?? [] : current.devices,
      commands: commands.ok ? commands.data?.commands ?? [] : current.commands,
      debugEnv: debugEnv.ok ? debugEnv.data : current.debugEnv,
      assistantStatus: health.ok ? current.assistantStatus : "error",
      statusText: health.ok ? current.statusText : "Ошибка",
      lastError: health.ok ? current.lastError : normalErrorMessage(health.error, "Backend недоступен")
    }));
  };

  useEffect(() => {
    playSound("startup");
    refreshStatus();
    const timer = window.setInterval(refreshStatus, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const applyCommandResult = (userText: string, data: CommandResult) => {
    const assistantText = resultText(data);
    const ttsUnavailable =
      data.tts && !isTtsQueued(data) && data.tts.ok === false
        ? `Команда выполнена, но Fish Audio не сработал: ${data.tts.error ?? "неизвестная ошибка"}`
        : data.tts?.fallback_used
          ? "Использован системный голос, Fish Audio недоступен."
          : null;
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

  const recordVoice = async () => {
    playSound("listening");
    setState((current) => ({ ...current, assistantStatus: "listening", statusText: "Слушаю", lastError: null }));
    const response = await api.recordCommand();
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

    const transcript = response.data.transcript?.trim();
    const assistantResult = response.data.assistant_result;
    if (transcript && assistantResult) {
      playSound("command_received");
      applyCommandResult(transcript, assistantResult);
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
      lastError: "STT не вернул текст команды"
    }));
    playSound("error");
  };

  const testMicrophone = async () => {
    playSound("listening");
    setState((current) => ({ ...current, assistantStatus: "listening", statusText: "Слушаю", lastError: null }));
    const response = await api.testMicrophone();
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
      lastError: data.heard_signal ? null : `Сигнал слишком тихий. RMS ${data.rms.toFixed(5)}`
    }));
    playSound(data.heard_signal ? "success" : "error");
  };

  const testVoice = async () => {
    playSound("command_start");
    setState((current) => ({ ...current, assistantStatus: "working", statusText: "Выполняю", lastError: null }));
    const response = await api.say("Голосовой модуль работает, сэр.");
    const assistantText = response.ok && response.data?.spoken ? "Голосовой модуль работает, сэр." : "Голосовой модуль недоступен, ответ показан текстом.";
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
          status: response.ok ? "completed" : "text_only",
          time: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
        },
        ...current.history
      ].slice(0, 24),
      lastError: response.ok && response.data?.audio_available === false ? "TTS недоступен, ответ показан текстом." : null
    }));
    playSound(response.ok ? "success" : "error");
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
