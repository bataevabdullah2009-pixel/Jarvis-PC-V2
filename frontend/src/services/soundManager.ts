export type SoundEventName =
  | "startup"
  | "wake"
  | "listening"
  | "command_received"
  | "command_start"
  | "success"
  | "error"
  | "notification";

export type SoundManagerSettings = {
  enabled: boolean;
  volume: number;
};

const STORAGE_KEY = "jarvis_pc_v2_ui_settings";

const defaultSettings: SoundManagerSettings = {
  enabled: true,
  volume: 0.65
};

const soundFiles: Record<SoundEventName, string> = {
  startup: "/sounds/startup.wav",
  wake: "/sounds/wake.wav",
  listening: "/sounds/listening.wav",
  command_received: "/sounds/command_received.wav",
  command_start: "/sounds/command_start.wav",
  success: "/sounds/success.wav",
  error: "/sounds/error.wav",
  notification: "/sounds/notification.wav"
};

const audioCache = new Map<SoundEventName, HTMLAudioElement>();

function clampVolume(value: unknown): number {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return defaultSettings.volume;
  return Math.max(0, Math.min(1, numeric));
}

export function getSoundSettings(): SoundManagerSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultSettings;
    const parsed = JSON.parse(raw) as { sounds?: Partial<SoundManagerSettings> };
    return {
      enabled: parsed.sounds?.enabled ?? defaultSettings.enabled,
      volume: clampVolume(parsed.sounds?.volume ?? defaultSettings.volume)
    };
  } catch {
    return defaultSettings;
  }
}

function getAudio(eventName: SoundEventName): HTMLAudioElement {
  const cached = audioCache.get(eventName);
  if (cached) return cached;
  const audio = new Audio(soundFiles[eventName]);
  audio.preload = "auto";
  audioCache.set(eventName, audio);
  return audio;
}

async function safePlay(audio: HTMLAudioElement): Promise<void> {
  try {
    audio.currentTime = 0;
    await audio.play();
  } catch {
    console.warn("Sound playback blocked");
  }
}

export function playSound(eventName: SoundEventName): void {
  const settings = getSoundSettings();
  if (!settings.enabled || settings.volume <= 0) return;

  const audio = getAudio(eventName);
  audio.volume = settings.volume;
  void safePlay(audio);
}

