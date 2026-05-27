export type ApiEnvelope<T> = {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string; details?: Record<string, unknown> } | null;
};

export type HealthData = {
  status: string;
  service: string;
};

export type AppStatusData = {
  app_name: string;
  status: string;
  ui: string;
  license: string;
};

export type LicenseStatusData = {
  enabled: boolean;
  blocking: boolean;
  status: string;
  message: string;
};

export type FullHealthData = {
  backend: string;
  settings: string;
  commands: string;
  voice: string;
  ai: string;
  tts: string;
  warnings: string[];
};

export type CommandAction = {
  type: string;
  target?: string;
  status?: string;
  playback_attempted?: boolean;
  actions?: CommandAction[];
};

export type CommandResult = {
  command_id: string;
  status: string;
  route: string;
  route_detail?: string;
  provider?: string;
  model?: string | null;
  openrouter_called?: boolean;
  fish_audio_called?: boolean;
  local_matched?: boolean;
  runtime_mode?: string;
  handled?: boolean;
  executed?: boolean;
  action?: string;
  text?: string;
  response_text: string;
  spoken: boolean;
  tts?: {
    ok?: boolean;
    provider?: string;
    spoken?: boolean;
    played?: boolean;
    audio_available?: boolean;
    fallback_used?: boolean;
    error?: string | null;
    status?: string;
    async?: boolean;
    pending_audio?: boolean;
    queued?: boolean;
    voice_locked?: boolean;
    voice_identity?: string;
    fix?: string | null;
    details?: Record<string, unknown>;
  };
  latency?: {
    router_ms?: number;
    intent_ms?: number;
    local_command_ms?: number;
    openrouter_ms?: number;
    ai_ms?: number;
    tts_ms?: number;
    tts_enqueue_ms?: number;
    tts_generate_ms?: number;
    tts_playback_started_ms?: number;
    total_ms?: number;
    total_response_ms?: number;
  };
  actions: CommandAction[];
  requires_confirmation: boolean;
  ok?: boolean;
  plan?: {
    status?: string;
    error_type?: string;
    status_code?: number;
    error_message?: string;
    fix?: string;
  } | null;
  error?: {
    code: string;
    type?: string;
    message: string;
    fix?: string;
    status_code?: number;
  } | null;
  error_type?: string;
  status_code?: number;
  fix?: string;
};

export type VoiceDependencyData = {
  sounddevice: { available: boolean; install_hint: string | null };
  numpy: { available: boolean; install_hint: string | null };
  microphone: { can_test: boolean };
  stt: { configured: boolean; provider: string | null };
  tts: {
    mode: string;
    providers: string[];
    fish_audio_configured?: boolean;
    offline_tts_available?: boolean;
    primary?: string;
    fallback?: string;
    fallback_enabled?: boolean;
    require_fish_audio?: boolean;
  };
};

export type VoiceDevice = {
  id: string;
  name: string;
  channels: number;
  default: boolean;
  default_samplerate: number;
};

export type MicrophoneTestData = {
  device_id: string;
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  rms: number;
  peak: number;
  heard_signal: boolean;
};

export type RecordCommandResponse = {
  ok: boolean;
  capture: {
    ok: boolean;
    rms: number;
    peak: number;
    heard_signal: boolean;
  };
  stt: {
    configured: boolean;
    provider: string | null;
    transcript: string | null;
    error_type: string | null;
    fix: string | null;
  };
  assistant_result: CommandResult | null;
  final_status: "recorded" | "no_audio" | "stt_not_configured" | "empty_transcript" | "sent_to_assistant" | "record_error";
};

export type MicDiagnosticsData = {
  sounddevice_available: boolean;
  numpy_available: boolean;
  default_input_device: VoiceDevice | null;
  input_devices: VoiceDevice[];
  windows_hint: string;
  can_record: boolean;
  fixes: string[];
};

export type TestCaptureData = {
  ok: boolean;
  device_id: string;
  sample_rate: number;
  channels: number;
  rms: number;
  peak: number;
  heard_signal: boolean;
  error_type: string | null;
  fix: string | null;
};

export type SttStatusData = {
  provider: string;
  vosk_available: boolean;
  model_path: string;
  model_exists: boolean;
  configured: boolean;
  language: string;
  fixes: string[];
};


export type SettingsData = {
  app_name: string;
  version: string;
  phase: string;
  debug_mode: boolean;
  chatgpt_url: string;
  news_url: string;
  news_rss_url?: string;
  workspace_project_path: string;
  open_terminal_with_workspace?: boolean;
  voice_profile: string;
  assistant_name?: string;
  assistant_display_name?: string;
  assistant_address_style?: string;
  voice_profile_id?: string;
  voice_profiles?: VoiceProfile[];
  voice_tone?: "calm" | "serious" | "fast" | "cinematic" | "friendly" | string;
  effective_voice_tone?: string;
  tone_instruction?: string;
  offline_mode: boolean;
  voice_wake_enabled?: boolean;
  clap_enabled?: boolean;
  runtime_mode?: "online" | "offline" | "hybrid";
  autostart_enabled?: boolean;
  ai_primary?: "groq" | "openrouter" | string;
  ai_fallback?: "groq" | "openrouter" | string;
  ai_allow_local_fallback?: boolean;
  voice_volume?: number;
  openrouter_configured: boolean;
  groq_configured?: boolean;
  groq_model?: string;
  openrouter_model?: string;
  fish_audio_configured: boolean;
  fish_audio_voice_configured: boolean;
  tts_primary?: string;
  tts_fallback?: string;
  tts_fallback_enabled?: boolean;
  tts_require_fish_audio?: boolean;
  listener_enabled?: boolean;
  listener_autostart?: boolean;
  listener_device_id?: string;
  wake_words?: string[] | string;
};

export type VoiceProfile = {
  id: string;
  name: string;
  provider: string;
  voice_id?: string;
  voice_id_masked?: string;
  tone: string;
  enabled: boolean;
};

export type CommandDefinition = {
  id: string;
  title?: string;
  name?: string;
  phrases?: string[];
  triggers?: string[];
  action_type?: string;
  action_value?: string;
  action?: string | { type: string; target?: string; value?: string };
  value?: string;
  enabled?: boolean;
  confirm_required?: boolean;
  confirmation_required?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type CommandPayload = {
  title: string;
  phrases: string[];
  action_type: string;
  action_value: string;
  enabled?: boolean;
  confirm_required?: boolean;
};

export type CommandsData = {
  commands: CommandDefinition[];
};

export type DiagnosticsData = {
  runtime: Record<string, unknown>;
  checks: Record<string, string>;
  voice: VoiceDependencyData;
  tts_status?: TTSStatusData;
  warnings: string[];
};

export type TTSStatusData = {
  primary: string;
  primary_ready: boolean;
  fallback: string;
  fallback_enabled?: boolean;
  fallback_ready: boolean;
  system_audio_ready: boolean;
  require_fish_audio?: boolean;
  voice_locked?: boolean;
  fallback_used?: boolean;
  last_provider_used?: string | null;
  last_error: string | null;
  voice_identity?: "jarvis" | "fallback" | "text_only" | string;
  queue_size?: number;
  active_job_id?: string | null;
  last_job_id?: string | null;
  last_job_age_seconds?: number;
  last_job_status?: "queued" | "started" | "playing" | "played" | "failed" | "cancelled" | "text_only" | "none" | string | null;
  last_provider?: string | null;
  last_error_type?: string | null;
  last_played_at?: number | null;
  stuck_jobs?: Array<{ job_id: string; status: string; age_seconds: number }>;
};

export type BuildInfoData = {
  git_sha?: string;
  git_branch?: string;
  built_at?: string;
  frontend_mode?: string;
  running_from_source?: boolean;
  packaged?: boolean;
  build_info_found?: boolean;
};

export type SayResult = {
  ok: boolean;
  provider: string;
  spoken: boolean;
  played?: boolean;
  audio_available: boolean;
  fallback_used?: boolean;
  error: string | null;
  fix?: string | null;
};

export type DebugEnvStatus = {
  env_loaded: boolean;
  paths_checked?: string[];
  paths_loaded?: string[];
  env_paths_checked: string[];
  env_paths_loaded?: string[];
  env_errors?: Record<string, string>;
  openrouter: {
    key_present: boolean;
    key_prefix: string | null;
    model: string;
    model_present?: boolean;
  };
  groq?: {
    key_present: boolean;
    key_prefix?: string | null;
    model: string;
    model_present?: boolean;
  };
  ai?: {
    primary: string;
    fallback: string;
    allow_local_fallback: boolean;
  };
  fish_audio: {
    key_present: boolean;
    key_prefix?: string | null;
    voice_id_present: boolean;
    voice_id_prefix: string | null;
  };
  tts?: {
    primary: string;
    fallback: string;
    fallback_enabled: boolean;
    require_fish_audio: boolean;
  };
};

export type VoiceProviderStatusData = {
  env_loaded: boolean;
  paths_loaded: string[];
  voice_profile: string;
  tts_primary: string;
  require_fish_audio: boolean;
  fallback_enabled: boolean;
  fish_key_present: boolean;
  fish_voice_id_present: boolean;
  selected_provider: "fish_audio" | "text_only";
  queue_size: number;
  active_job_id: string | null;
  last_job_id: string | null;
  last_job_status: string;
  last_job_age_seconds?: number;
  last_provider: string;
  last_error_type: string | null;
  last_error: string | null;
  fixes: string[];
};

export type ProviderTestResult = {
  ok: boolean;
  provider: string;
  model?: string;
  status_code?: number | null;
  response_preview?: string;
  voice_id_present?: boolean;
  audio_bytes?: number;
  played?: boolean;
  format?: string;
  latency_ms?: number;
  error_type?: string;
  error_message?: string;
  fix?: string;
};

export type AIProviderStatusData = {
  primary: string;
  fallback: string;
  groq: {
    key_present: boolean;
    model: string;
    available: boolean;
    last_error_type?: string | null;
    latency_ms?: number | null;
  };
  openrouter: {
    key_present: boolean;
    model: string;
    available: boolean;
    last_error_type?: string | null;
    latency_ms?: number | null;
  };
};

export type LocalVoiceStatusData = Record<
  string,
  {
    enabled: boolean;
    available: boolean;
    model_exists?: boolean;
    model_path?: string;
    api_url?: string;
    install_hint?: string;
  }
>;

export type EventPayload = {
  event_id?: string;
  type: string;
  timestamp?: string;
  payload: Record<string, unknown> | Array<Record<string, unknown>>;
};

export const API_BASE = import.meta.env.VITE_JARVIS_API_BASE || "http://127.0.0.1:18000";
export const WS_EVENTS_URL = API_BASE.replace(/^http/, "ws") + "/ws/events";

function friendlyFetchMessage(path: string, error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  console.warn("[JARVIS_FETCH_ERROR]", path, raw);
  const hint = "Backend недоступен. Проверьте, запущен ли python run_backend.py. Откройте /debug/startup или /health.";
  if (path.includes("/voice/say") || path.includes("/voice/tts-status")) {
    return "TTS недоступен. " + hint;
  }
  if (path.includes("/voice/")) {
    return "Голосовой модуль недоступен. " + hint;
  }
  if (path.includes("/news/") || path.includes("/scenarios/news")) {
    return "Новости недоступны. " + hint;
  }
  if (path.includes("/assistant/command") || path.includes("/assistant/ask")) {
    return "Backend недоступен. " + hint;
  }
  return hint;
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      },
      ...init
    });
    return response.json() as Promise<ApiEnvelope<T>>;
  } catch (error) {
    return {
      ok: false,
      data: null,
      error: {
        code: "NETWORK_ERROR",
        message: friendlyFetchMessage(path, error),
        details: { path }
      }
    };
  }
}

async function rawRequest<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      },
      ...init
    });
    return { ok: response.ok, data: (await response.json()) as T, error: null };
  } catch (error) {
    return {
      ok: false,
      data: null,
      error: {
        code: "NETWORK_ERROR",
        message: friendlyFetchMessage(path, error),
        details: { path }
      }
    };
  }
}

export const api = {
  health: () => request<HealthData>("/health"),
  appStatus: () => request<AppStatusData>("/app/status"),
  buildInfo: () => request<BuildInfoData>("/runtime/build-info"),
  fullHealth: () => request<FullHealthData>("/health/full"),
  licenseStatus: () => request<LicenseStatusData>("/license/status"),
  settings: () => request<SettingsData>("/settings"),
  patchSettings: (patch: Partial<SettingsData>) =>
    request<SettingsData>("/settings", {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),
  commands: () => request<CommandsData>("/commands"),
  createCommand: (payload: CommandPayload) =>
    request<CommandDefinition>("/commands", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateCommand: (commandId: string, payload: Partial<CommandPayload>) =>
    request<CommandDefinition>(`/commands/${encodeURIComponent(commandId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteCommand: (commandId: string) =>
    request<{ deleted: boolean; command_id: string }>(`/commands/${encodeURIComponent(commandId)}`, {
      method: "DELETE"
    }),
  diagnostics: () =>
    request<DiagnosticsData>("/diagnostics/full-test", {
      method: "POST",
      body: JSON.stringify({})
    }),
  voiceDependencies: () => request<VoiceDependencyData>("/voice/dependency-check"),
  ttsStatus: () => request<TTSStatusData>("/voice/tts-status"),
  ttsReset: () =>
    request<TTSStatusData>("/voice/tts-reset", {
      method: "POST"
    }),
  say: (text: string) =>
    request<SayResult>("/voice/say", {
      method: "POST",
      body: JSON.stringify({ text })
    }),
  debugEnvStatus: () => rawRequest<DebugEnvStatus>("/debug/env-status"),
  aiProviderStatus: () => request<AIProviderStatusData>("/debug/ai-provider-status"),
  voiceProviderStatus: () => request<VoiceProviderStatusData>("/debug/voice-provider-status"),
  localVoiceStatus: () => request<LocalVoiceStatusData>("/debug/local-voice-status"),
  testJarvisVoice: (text = "Проверка голоса Джарвиса. Я на связи, сэр.") =>
    request<ProviderTestResult>("/debug/test-jarvis-voice", {
      method: "POST",
      body: JSON.stringify({ text })
    }),
  testOpenRouter: () =>
    rawRequest<ProviderTestResult>("/debug/test-openrouter", {
      method: "POST",
      body: JSON.stringify({})
    }),
  testGroq: () =>
    request<ProviderTestResult>("/debug/test-groq", {
      method: "POST",
      body: JSON.stringify({ text: "Ответь одним словом: OK" })
    }),
  testFishAudio: () =>
    rawRequest<ProviderTestResult>("/debug/test-fish-audio", {
      method: "POST",
      body: JSON.stringify({})
    }),
  testFullPipeline: (text = "Джарвис как дела?") =>
    rawRequest<CommandResult>("/debug/test-full-pipeline", {
      method: "POST",
      body: JSON.stringify({ text })
    }),
  voiceDevices: () => request<{ input_devices: VoiceDevice[] }>("/voice/devices"),
  testMicrophone: (deviceId?: string) =>
    request<MicrophoneTestData>("/voice/test-microphone", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId ?? "default", duration_seconds: 3 })
    }),
  recordCommand: (deviceId?: string, maxSeconds?: number) =>
    request<RecordCommandResponse>("/voice/record-command", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId ?? "default", max_seconds: maxSeconds ?? 5, send_to_assistant: true })
    }),
  micDiagnostics: () => request<MicDiagnosticsData>("/voice/mic-diagnostics"),
  testCapture: (deviceId?: string, durationSeconds?: number) =>
    request<TestCaptureData>("/voice/test-capture", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId ?? "default", duration_seconds: durationSeconds ?? 3 })
    }),
  sttStatus: () => request<SttStatusData>("/voice/stt-status"),
  listenerStatus: () => request<any>("/voice/listener-status"),
  listenerStart: (deviceId: string, wakeWord: boolean, clap: boolean) =>
    request<any>("/voice/listener-start", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, wake_word: wakeWord, clap })
    }),
  listenerStop: () =>
    request<any>("/voice/listener-stop", {
      method: "POST"
    }),
  calibrateMic: (deviceId: string, silenceSeconds = 2, speechSeconds = 3) =>
    request<any>("/voice/calibrate-mic", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, silence_seconds: silenceSeconds, speech_seconds: speechSeconds })
    }),
  sendCommand: (text: string) =>
    request<CommandResult>("/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ text, speak: true, source: "hud", context: {} })
    }),
  scenario: (name: "welcome-home" | "news" | "workspace" | "music") => {
    const pathByName = {
      "welcome-home": "/scenarios/welcome-home",
      news: "/news/open-and-read",
      workspace: "/scenarios/workspace",
      music: "/scenarios/music"
    };
    return request<CommandResult | Record<string, unknown>>(pathByName[name], {
      method: "POST",
      body: JSON.stringify({ context: {} })
    });
  }
};
