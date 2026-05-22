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
  };
  latency?: {
    router_ms: number;
    ai_ms: number;
    tts_ms: number;
    total_ms: number;
  };
  actions: CommandAction[];
  requires_confirmation: boolean;
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

export type SettingsData = {
  app_name: string;
  version: string;
  phase: string;
  debug_mode: boolean;
  chatgpt_url: string;
  news_url: string;
  news_rss_url?: string;
  workspace_project_path: string;
  voice_profile: string;
  offline_mode: boolean;
  voice_wake_enabled?: boolean;
  clap_enabled?: boolean;
  runtime_mode?: "online" | "offline" | "hybrid";
  autostart_enabled?: boolean;
  voice_volume?: number;
  openrouter_configured: boolean;
  fish_audio_configured: boolean;
  fish_audio_voice_configured: boolean;
  tts_primary?: string;
  tts_fallback?: string;
  tts_fallback_enabled?: boolean;
  tts_require_fish_audio?: boolean;
};

export type CommandDefinition = {
  id: string;
  name?: string;
  phrases?: string[];
  triggers?: string[];
  action?: string | { type: string; target?: string; value?: string };
  value?: string;
  confirmation_required?: boolean;
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
  last_provider_used?: string | null;
  last_error: string | null;
};

export type SayResult = {
  ok: boolean;
  provider: string;
  spoken: boolean;
  played?: boolean;
  audio_available: boolean;
  fallback_used?: boolean;
  error: string | null;
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

export type EventPayload = {
  event_id?: string;
  type: string;
  timestamp?: string;
  payload: Record<string, unknown> | Array<Record<string, unknown>>;
};

const API_BASE = import.meta.env.VITE_JARVIS_API_BASE ?? "http://127.0.0.1:8000";
export const WS_EVENTS_URL = API_BASE.replace(/^http/, "ws") + "/ws/events";

function friendlyFetchMessage(path: string, error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  console.warn("[JARVIS_FETCH_ERROR]", path, raw);
  if (path.includes("/voice/say") || path.includes("/voice/tts-status")) {
    return "TTS недоступен";
  }
  if (path.includes("/voice/")) {
    return "Голосовой модуль недоступен";
  }
  if (path.includes("/news/") || path.includes("/scenarios/news")) {
    return "Новости недоступны";
  }
  if (path.includes("/assistant/command") || path.includes("/assistant/ask")) {
    return "Backend недоступен";
  }
  return "Backend недоступен";
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
  buildInfo: () => request<Record<string, unknown>>("/runtime/build-info"),
  fullHealth: () => request<FullHealthData>("/health/full"),
  licenseStatus: () => request<LicenseStatusData>("/license/status"),
  settings: () => request<SettingsData>("/settings"),
  patchSettings: (patch: Partial<SettingsData>) =>
    request<SettingsData>("/settings", {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),
  commands: () => request<CommandsData>("/commands"),
  diagnostics: () =>
    request<DiagnosticsData>("/diagnostics/full-test", {
      method: "POST",
      body: JSON.stringify({})
    }),
  voiceDependencies: () => request<VoiceDependencyData>("/voice/dependency-check"),
  ttsStatus: () => request<TTSStatusData>("/voice/tts-status"),
  say: (text: string) =>
    request<SayResult>("/voice/say", {
      method: "POST",
      body: JSON.stringify({ text })
    }),
  debugEnvStatus: () => rawRequest<DebugEnvStatus>("/debug/env-status"),
  testOpenRouter: () =>
    rawRequest<ProviderTestResult>("/debug/test-openrouter", {
      method: "POST",
      body: JSON.stringify({})
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
  testMicrophone: () =>
    request<MicrophoneTestData>("/voice/test-microphone", {
      method: "POST",
      body: JSON.stringify({ device_id: "default", duration_seconds: 1 })
    }),
  recordCommand: () =>
    request<{
      transcript: string | null;
      rms: number | null;
      peak: number | null;
      assistant_result: CommandResult | null;
    }>("/voice/record-command", {
      method: "POST",
      body: JSON.stringify({ device_id: "default", max_seconds: 4, send_to_assistant: true })
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
      music: "/scenarios/welcome-home"
    };
    return request<CommandResult | Record<string, unknown>>(pathByName[name], {
      method: "POST",
      body: JSON.stringify({ context: {} })
    });
  }
};
