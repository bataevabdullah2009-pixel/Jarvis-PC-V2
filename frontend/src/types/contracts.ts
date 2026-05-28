export interface ListenerStatus {
  status: string; // "idle" | "listening" | "speaking" | "blocked" | "error"
  device_id: string;
  device_name: string;
  wake_words: string[];
  is_listening: boolean;
  error_message: string | null;
  fixes: string[];
}

export interface AIProviderStatus {
  provider: string; // "groq" | "openrouter" | "local"
  model: string;
  configured: boolean;
  latency_ms: number | null;
  available: boolean;
}

export interface VoiceProviderStatus {
  provider: string; // "fish_audio" | "piper_local" | "pyttsx3"
  voice_id: string | null;
  configured: boolean;
  voice_tone: string; // "calm" | "serious" | "fast" | "cinematic" | "friendly"
}

export interface TTSStatus {
  status: string; // "ready" | "speaking" | "error"
  queue_size: number;
  active: boolean;
}

export interface RuntimeStatus {
  app_name: string;
  version: string;
  phase: string;
  debug_mode: boolean;
  listener: ListenerStatus;
  ai: AIProviderStatus;
  voice: VoiceProviderStatus;
  tts: TTSStatus;
}

export interface SettingsData {
  assistant_name: string;
  assistant_display_name: string;
  assistant_address_style: string;
  voice_wake_enabled: boolean;
  clap_enabled: boolean;
  autostart_enabled: boolean;
  voice_volume: number;
  ai_primary: string;
  ai_fallback: string;
  tts_primary: string;
  cooldown_ms: number;
  listener_device_id: string;
  wake_words: string[];
}

export interface CommandData {
  id: string;
  name: string;
  phrases: string[];
  action_type: string; // "file" | "url" | "scenario" | "keypress" | "shell"
  action_target: string;
  enabled: boolean;
}

export interface AssistantResult {
  query: string;
  response: string;
  command_triggered: string | null;
  success: boolean;
  latency: {
    router_ms?: number;
    ai_ms?: number;
    tts_ms?: number;
    total_ms?: number;
    [key: string]: number | undefined;
  };
}
