export type AccentPreset = "blue" | "purple" | "cyan" | "green" | "red" | "orange" | "custom";
export type MusicMode = "local_file" | "browser_search" | "direct_url";
export type MusicProvider = "KION/MTS" | "Yandex" | "Custom";
export type LocalScenarioName = "welcome-home" | "news" | "workspace";

export type SoundSettings = {
  enabled: boolean;
  volume: number;
};

export type AppearanceSettings = {
  accentPreset: AccentPreset;
  accentColor: string;
  theme: "dark";
};

export type WorkspaceAction = {
  id: string;
  type: "open_url" | "open_app" | "open_folder";
  value: string;
};

export type WorkspaceScenarioSettings = {
  id: "workspace";
  name: string;
  phrases: string[];
  openChatGPT: boolean;
  chatgptUrl: string;
  openVSCode: boolean;
  projectPath: string;
  openTerminal: boolean;
  browserLinks: string[];
  customApps: string[];
  customSites: string[];
  actions: WorkspaceAction[];
  responseText: string;
};

export type WelcomeHomeScenarioSettings = {
  id: "welcome-home";
  name: string;
  phrases: string[];
  responseText: string;
  musicMode: MusicMode;
  trackName: string;
  localFilePath: string;
  musicProvider: MusicProvider;
  searchUrlTemplate: string;
  directTrackUrl: string;
  tryAutoplay: boolean;
  fallbackMessage: string;
};

export type NewsScenarioSettings = {
  id: "news";
  name: string;
  phrases: string[];
  newsUrl: string;
  rssSources: string[];
  headlineCount: 3 | 5 | 10;
  openBrowser: boolean;
  readAloud: boolean;
  responseText: string;
};

export type LocalSettings = {
  appearance: AppearanceSettings;
  sounds: SoundSettings;
  workspace: WorkspaceScenarioSettings;
  welcomeHome: WelcomeHomeScenarioSettings;
  news: NewsScenarioSettings;
};

const STORAGE_KEY = "jarvis_pc_v2_ui_settings";

export const accentPresets: Record<Exclude<AccentPreset, "custom">, string> = {
  blue: "#4F7CFF",
  purple: "#6C5CFF",
  cyan: "#00B8FF",
  green: "#36D399",
  red: "#FF5C7A",
  orange: "#FF9F43"
};

export const defaultLocalSettings: LocalSettings = {
  appearance: {
    accentPreset: "purple",
    accentColor: "#6C5CFF",
    theme: "dark"
  },
  sounds: {
    enabled: true,
    volume: 0.65
  },
  workspace: {
    id: "workspace",
    name: "Моя рабочая среда",
    phrases: ["настрой мою среду", "рабочий режим", "запусти рабочую среду"],
    openChatGPT: true,
    chatgptUrl: "https://chatgpt.com",
    openVSCode: true,
    projectPath: "C:\\Jarvis\\jarvis-car",
    openTerminal: false,
    browserLinks: [],
    customApps: [],
    customSites: [],
    actions: [],
    responseText: "Рабочая среда готова, сэр."
  },
  welcomeHome: {
    id: "welcome-home",
    name: "Я вернулся",
    phrases: ["я вернулся", "я дома", "джарвис я вернулся"],
    responseText: "С возвращением, сэр.",
    musicMode: "browser_search",
    trackName: "Back in Black",
    localFilePath: "",
    musicProvider: "KION/MTS",
    searchUrlTemplate: "https://music.kion.ru/search?text={query}",
    directTrackUrl: "",
    tryAutoplay: true,
    fallbackMessage: "Сайт заблокировал автозапуск. Я открыл трек, нажмите Play."
  },
  news: {
    id: "news",
    name: "Новости",
    phrases: ["есть новости", "что нового", "джарвис новости"],
    newsUrl: "https://news.google.com/topstories?hl=ru&gl=RU&ceid=RU:ru",
    rssSources: ["https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru"],
    headlineCount: 5,
    openBrowser: true,
    readAloud: false,
    responseText: "Новости открыты, сэр."
  }
};

function mergeSettings(value: Partial<LocalSettings>): LocalSettings {
  return {
    appearance: { ...defaultLocalSettings.appearance, ...(value.appearance ?? {}) },
    sounds: { ...defaultLocalSettings.sounds, ...(value.sounds ?? {}) },
    workspace: { ...defaultLocalSettings.workspace, ...(value.workspace ?? {}) },
    welcomeHome: { ...defaultLocalSettings.welcomeHome, ...(value.welcomeHome ?? {}) },
    news: { ...defaultLocalSettings.news, ...(value.news ?? {}) }
  };
}

export function loadLocalSettings(): LocalSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? mergeSettings(JSON.parse(raw) as Partial<LocalSettings>) : defaultLocalSettings;
  } catch {
    return defaultLocalSettings;
  }
}

export function saveLocalSettings(settings: LocalSettings): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function normalizeCommand(text: string): string {
  return text
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[,.!?;:()[\]{}"'«»]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^джарвис\s+/, "");
}

export function matchLocalScenario(text: string, settings: LocalSettings): LocalScenarioName | null {
  const normalized = normalizeCommand(text);
  const entries: Array<[LocalScenarioName, string[]]> = [
    ["welcome-home", settings.welcomeHome.phrases],
    ["workspace", settings.workspace.phrases],
    ["news", settings.news.phrases]
  ];
  for (const [name, phrases] of entries) {
    const normalizedPhrases = phrases.map(normalizeCommand).filter(Boolean);
    if (normalizedPhrases.some((phrase) => normalized === phrase || normalized.includes(phrase))) {
      return name;
    }
  }
  return null;
}

function encodeQuery(value: string): string {
  return encodeURIComponent(value.trim() || "Back in Black");
}

export async function runLocalScenario(name: LocalScenarioName, settings: LocalSettings): Promise<{ ok: boolean; message: string; warning?: string }> {
  const native = window.jarvisNative;

  if (name === "welcome-home") {
    const config = settings.welcomeHome;
    if (config.musicMode === "local_file") {
      if (!config.localFilePath.trim()) {
        return { ok: true, message: config.responseText, warning: "Локальный mp3/wav ещё не выбран." };
      }
      const result = await native?.openPath?.(config.localFilePath);
      return result?.ok
        ? { ok: true, message: config.responseText }
        : { ok: true, message: config.responseText, warning: result?.message ?? "Не удалось открыть локальный файл." };
    }

    if (config.musicMode === "direct_url") {
      if (!config.directTrackUrl.trim()) {
        return { ok: true, message: config.responseText, warning: "Прямая ссылка на трек не задана." };
      }
      await native?.openUrl?.(config.directTrackUrl);
      if (config.tryAutoplay) {
        await native?.mediaPlayPause?.();
      }
      return { ok: true, message: config.responseText, warning: config.tryAutoplay ? config.fallbackMessage : undefined };
    }

    const encodedTrack = encodeQuery(config.trackName);
    const url = config.searchUrlTemplate
      .replace(/\{query\}/g, encodedTrack)
      .replace(/\{text\}/g, encodedTrack)
      .replace(/\{q\}/g, encodedTrack);
    await native?.openUrl?.(url);
    if (config.tryAutoplay) {
      await native?.mediaPlayPause?.();
    }
    return { ok: true, message: config.responseText, warning: config.tryAutoplay ? config.fallbackMessage : undefined };
  }

  if (name === "workspace") {
    const config = settings.workspace;
    if (config.openChatGPT && config.chatgptUrl.trim()) {
      await native?.openUrl?.(config.chatgptUrl);
    }
    if (config.openVSCode) {
      await native?.openCommand?.("code", config.projectPath.trim() ? [config.projectPath] : []);
    }
    if (config.openTerminal) {
      await native?.openCommand?.("cmd", config.projectPath.trim() ? ["/k", `cd /d ${config.projectPath}`] : ["/k"]);
    }
    if (config.projectPath.trim()) {
      await native?.openPath?.(config.projectPath);
    }
    for (const link of [...config.browserLinks, ...config.customSites]) {
      if (link.trim()) {
        await native?.openUrl?.(link);
      }
    }
    for (const app of config.customApps) {
      if (app.trim()) {
        await native?.openCommand?.(app, []);
      }
    }
    for (const action of config.actions) {
      if (action.type === "open_url") await native?.openUrl?.(action.value);
      if (action.type === "open_folder") await native?.openPath?.(action.value);
      if (action.type === "open_app") await native?.openCommand?.(action.value, []);
    }
    return { ok: true, message: config.responseText };
  }

  const config = settings.news;
  if (config.openBrowser && config.newsUrl.trim()) {
    await native?.openUrl?.(config.newsUrl);
  }
  return {
    ok: true,
    message: config.responseText,
    warning: config.readAloud ? "Новости открыты, но сводка сейчас недоступна без RSS-прокси в backend." : undefined
  };
}
