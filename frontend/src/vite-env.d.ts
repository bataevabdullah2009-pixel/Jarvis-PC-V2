/// <reference types="vite/client" />

interface Window {
  jarvisNative?: {
    openLogs?: () => Promise<void>;
    openPath?: (path: string) => Promise<{ ok: boolean; message?: string }>;
    openUrl?: (url: string) => Promise<{ ok: boolean; message?: string }>;
    openCommand?: (command: string, args?: string[]) => Promise<{ ok: boolean; message?: string }>;
    pickAudioFile?: () => Promise<{ canceled: boolean; path?: string }>;
    mediaPlayPause?: () => Promise<{ ok: boolean; message?: string }>;
  };
}
