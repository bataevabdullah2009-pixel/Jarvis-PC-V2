import {
  Activity,
  Bot,
  CheckCircle2,
  Command,
  FolderOpen,
  Headphones,
  Home,
  Link,
  Mic,
  Music2,
  Newspaper,
  Palette,
  Play,
  Plus,
  Save,
  Send,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Volume1,
  Volume2,
  Wrench
} from "lucide-react";
import { CSSProperties, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { AppState, Screen } from "./App";
import { SettingsData } from "../api/client";
import {
  accentPresets,
  defaultLocalSettings,
  loadLocalSettings,
  LocalSettings,
  MusicMode,
  saveLocalSettings,
  WorkspaceAction
} from "../lib/localSettings";
import { playSound, type SoundEventName } from "../services/soundManager";

type Props = {
  state: AppState;
  onScreen: (screen: Screen) => void;
  onCommand: (text: string) => Promise<void>;
  onScenario: (name: "welcome-home" | "news" | "workspace") => Promise<void>;
  onRecordVoice: () => Promise<void>;
  onTestMicrophone: () => Promise<void>;
  onTestVoice: () => Promise<void>;
  onTestOpenRouter: () => Promise<void>;
  onTestFishAudio: () => Promise<void>;
  onTestAiFallback: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onDiagnostics: () => Promise<void>;
  onPatchSettings: (patch: Partial<SettingsData>) => Promise<void>;
};

const navItems: Array<{ screen: Screen; label: string; icon: typeof Home }> = [
  { screen: "home", label: "Главная", icon: Home },
  { screen: "commands", label: "Команды", icon: Command },
  { screen: "scenarios", label: "Сценарии", icon: Sparkles },
  { screen: "myCommands", label: "Мои команды", icon: Bot },
  { screen: "voices", label: "Голоса", icon: Headphones },
  { screen: "environment", label: "Настройки среды", icon: FolderOpen },
  { screen: "settings", label: "Настройки", icon: Settings },
  { screen: "diagnostics", label: "Диагностика", icon: Activity }
];

const quickCommands = ["Я вернулся", "Рабочий режим", "Проверить микрофон", "Проверить голос", "Добавить команду"];

const statusLabel = {
  ready: "Готов",
  listening: "Слушаю",
  working: "Выполняю",
  done: "Выполнено",
  warning: "Выполнено",
  error: "Ошибка"
};

export function MinimalUI({
  state,
  onScreen,
  onCommand,
  onScenario,
  onRecordVoice,
  onTestMicrophone,
  onTestVoice,
  onTestOpenRouter,
  onTestFishAudio,
  onTestAiFallback,
  onRefresh,
  onDiagnostics,
  onPatchSettings
}: Props) {
  const [command, setCommand] = useState("");
  const [localSettings, setLocalSettings] = useState<LocalSettings>(() => loadLocalSettings());
  const [savedText, setSavedText] = useState("Сохранено локально");

  const latency = state.lastResult?.latency;
  const ttsGenerateMs = latency?.tts_generate_ms ?? latency?.tts_ms ?? null;

  const voiceLocked =
    Boolean(state.ttsStatus?.voice_locked) ||
    Boolean(state.debugEnv?.tts?.require_fish_audio) ||
    Boolean(state.lastResult?.tts?.voice_locked);

  useEffect(() => {
    const accent = localSettings.appearance.accentColor || defaultLocalSettings.appearance.accentColor;
    document.documentElement.style.setProperty("--accent", accent);
    document.documentElement.style.setProperty("--accent-2", accent === "#00B8FF" ? "#6C5CFF" : "#00B8FF");
    document.documentElement.style.setProperty("--accent-soft", `${accent}29`);
  }, [localSettings.appearance]);

  const persist = (next: LocalSettings) => {
    setLocalSettings(next);
    saveLocalSettings(next);
    setSavedText("Сохранено локально");
  };

  const updateLocal = (patch: Partial<LocalSettings>) => {
    persist({ ...localSettings, ...patch });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = command.trim();
    if (!text) return;
    setCommand("");
    await onCommand(text);
  };

  const openrouterStatus = useMemo(() => {
    if (state.lastResult) {
      const called = state.lastResult.openrouter_called;
      const plan = state.lastResult.plan;
      const errorObj = state.lastResult.error;
      const errorType = errorObj?.type || plan?.error_type || state.lastResult.error_type;
      const statusCode = state.lastResult.status_code || plan?.status_code || errorObj?.status_code;

      if (called) {
        if (errorType === "rate_limited" || statusCode === 429) {
          return "rate limited";
        }
        if (errorType === "timeout") {
          return "timeout";
        }
        if (statusCode === 200 || (!errorType && !statusCode && state.lastResult.ok)) {
          return "called / 200 OK";
        }
        if (statusCode === 401 || errorType === "invalid_key") {
          return "called / 401 invalid key";
        }
        if (statusCode === 402 || errorType === "no_credits_or_payment_required") {
          return "called / 402 no credits";
        }
        if (statusCode === 403 || errorType === "forbidden") {
          return "called / 403 forbidden";
        }
        if (statusCode === 404 || errorType === "model_not_found") {
          return "called / 404 model not found";
        }
        if (statusCode) {
          return `called / ${statusCode} error`;
        }
        return "called / error";
      } else {
        if (errorType === "key_missing" || state.lastResult.route_detail === "ai_fallback:missing_key") {
          return "key missing";
        }
        if (errorType === "model_missing") {
          return "model missing";
        }
      }
    }

    if (state.debugEnv?.openrouter) {
      if (!state.debugEnv.openrouter.key_present) {
        return "key missing";
      }
      if (!state.debugEnv.openrouter.model_present) {
        return "model missing";
      }
    } else if (state.settings) {
      if (!state.settings.openrouter_configured) {
        return "key missing";
      }
    }

    return "not called";
  }, [state.lastResult, state.debugEnv, state.settings]);

  const diagnosticFix = useMemo(() => {
    if (!state.lastResult) return null;
    return state.lastResult.error?.fix || state.lastResult.plan?.fix || state.lastResult.fix || null;
  }, [state.lastResult]);

  const routeSummary = state.lastResult
    ? `${state.lastResult.route} | OpenRouter: ${openrouterStatus} | TTS: ${state.lastResult.tts?.provider ?? "none"}${state.lastResult.tts?.status ? `/${state.lastResult.tts.status}` : ""} | ${state.lastResult.latency?.total_ms ?? 0} ms`
    : "ожидание";

  return (
    <main className="minimal-app">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <div className="lux-shape" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>

      <aside className="sidebar">
        <div className="brand-mark" title="JARVIS PC V2">
          <span>J</span>
        </div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={state.screen === item.screen ? "active" : ""}
                key={item.screen}
                type="button"
                onClick={() => {
                  onScreen(item.screen);
                  if (item.screen === "diagnostics") onDiagnostics();
                }}
                title={item.label}
              >
                <Icon size={19} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="build-label" title={state.buildInfo?.git_sha ?? "dev"}>
            Build: {(() => {
              const info = state.buildInfo;
              if (!info) return "dev";
              if (info.git_sha && info.git_sha !== "unknown") return info.git_sha;
              if (info.packaged) {
                if (info.build_info_found === false) {
                  return "BUILD_INFO.json not found";
                }
                if (!info.git_sha || info.git_sha === "unknown") {
                  return "backend did not return git_sha";
                }
                return "running old exe";
              }
              return "dev";
            })()}
          </div>
          <div className="build-date">{state.buildInfo?.built_at?.split(' ')[0] ?? ""}</div>
        </div>
      </aside>

      <section className="workspace">
        <header className="app-header">
          <div>
            <p className="eyebrow">JARVIS PC V2</p>
            <h1>Minimal Assistant</h1>
          </div>
          <div className="header-status">
            <span>{state.license?.message ?? "Лицензия отключена"}</span>
            <strong>{state.appStatus?.status ?? "local"}</strong>
          </div>
        </header>

        {state.screen === "home" && (
          <section className="home-layout">
            <section className="panel main-window">
              <div className="panel-heading split">
                <div>
                  <p className="eyebrow">Основное окно</p>
                  <h2>История команд</h2>
                </div>
                <span className={`assistant-state state-${state.assistantStatus}`}>{statusLabel[state.assistantStatus]}</span>
              </div>

              <div className="reply-card">
                <span>JARVIS</span>
                <p>{state.lastResult?.response_text ?? "Готов к команде, сэр."}</p>
                
                {state.lastResult && (
                  <div className="assistant-metrics-card" style={{
                    marginTop: "12px",
                    padding: "8px 12px",
                    background: "rgba(0, 0, 0, 0.25)",
                    borderRadius: "6px",
                    fontSize: "0.8rem",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px"
                  }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
                      <div>
                        <span style={{ color: "rgba(255, 255, 255, 0.4)" }}>AI: </span>
                        <strong style={{ color: "var(--accent)" }}>
                          {state.lastResult.provider === "openrouter" 
                            ? `openrouter / ${state.lastResult.model || "unknown"} / ${state.lastResult.latency?.openrouter_ms ?? state.lastResult.latency?.ai_ms ?? 0} ms` 
                            : state.lastResult.local_matched 
                              ? `local / ${state.lastResult.latency?.local_command_ms ?? 0} ms` 
                              : "none"}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "rgba(255, 255, 255, 0.4)" }}>Voice: </span>
                        <strong style={{ color: "var(--accent-2)" }}>
                          {state.lastResult.tts?.provider ?? "none"} 
                          {state.lastResult.tts?.status ? ` (${state.lastResult.tts?.status})` : ""}
                          {ttsGenerateMs ? ` / ${ttsGenerateMs} ms` : ""}
                        </strong>
                      </div>
                    </div>
                    
                    {/* Fallback voice used yellow warning */}
                    {state.lastResult.tts?.fallback_used && (
                      <div style={{ color: "#FFE054", fontWeight: 500, display: "flex", alignItems: "center", gap: "4px" }}>
                        ⚠️ Использован резервный голос: {state.lastResult.tts?.provider ?? "pyttsx3/edge_tts"}
                      </div>
                    )}
                    
                    {/* Locked voice but Fish failed warning */}
                    {state.lastResult.tts?.provider === "text_only" && voiceLocked && (
                      <div style={{ color: "#FF5E5E", fontWeight: 500, display: "flex", alignItems: "center", gap: "4px" }}>
                        ⚠️ Голос Джарвиса недоступен. Чужой голос отключён.
                      </div>
                    )}
                  </div>
                )}

                {state.lastError && <strong>{state.lastError}</strong>}
              </div>

              <HistoryPanel state={state} compact />

              <form className="command-form" onSubmit={submit}>
                <input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Введите команду" />
                <button type="submit" title="Отправить">
                  <Send size={18} />
                </button>
                <button type="button" onClick={onRecordVoice} title="Микрофон">
                  <Mic size={18} />
                </button>
              </form>

              <div className="quick-actions">
                {quickCommands.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => {
                      if (item === "Проверить микрофон") onTestMicrophone();
                      else if (item === "Проверить голос") onTestVoice();
                      else if (item === "Добавить команду") onScreen("myCommands");
                      else onCommand(item);
                    }}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </section>

            <ControlPanel state={state} onPatchSettings={onPatchSettings} onRefresh={onRefresh} />
          </section>
        )}

        {state.screen === "commands" && <CommandsPanel state={state} />}
        {state.screen === "scenarios" && (
          <ScenariosPanel settings={localSettings} onChange={updateLocal} onScenario={onScenario} savedText={savedText} />
        )}
        {state.screen === "myCommands" && <MyCommandsPanel state={state} />}
        {state.screen === "voices" && <VoicesPanel state={state} onTestMicrophone={onTestMicrophone} onTestVoice={onTestVoice} />}
        {state.screen === "environment" && (
          <section className="panel page-panel">
            <ScenarioHeader title="Моя рабочая среда" icon={<FolderOpen size={18} />} savedText={savedText} />
            <WorkspaceEditor settings={localSettings} onChange={updateLocal} onTest={() => onScenario("workspace")} />
          </section>
        )}
        {state.screen === "settings" && (
          <SettingsPanel state={state} localSettings={localSettings} onLocalChange={updateLocal} onPatchSettings={onPatchSettings} savedText={savedText} />
        )}
        {state.screen === "diagnostics" && (
          <DiagnosticsPanel
            state={state}
            onDiagnostics={onDiagnostics}
            onTestMicrophone={onTestMicrophone}
            onTestOpenRouter={onTestOpenRouter}
            onTestFishAudio={onTestFishAudio}
            onTestAiFallback={onTestAiFallback}
          />
        )}

        <footer className="status-strip">
          <div>
            <span>Маршрут</span>
            <strong>{routeSummary}</strong>
          </div>
          <div>
            <span>Backend</span>
            <strong>{state.health?.backend ?? "checking"}</strong>
          </div>
          <div>
            <span>Статус</span>
            <strong>{state.statusText}</strong>
          </div>
          {diagnosticFix && (
            <div style={{ color: "#FF5E5E" }}>
              <span>Решение</span>
              <strong title={diagnosticFix}>{diagnosticFix}</strong>
            </div>
          )}
        </footer>
      </section>
    </main>
  );
}

function ControlPanel({ state, onPatchSettings, onRefresh }: { state: AppState; onPatchSettings: Props["onPatchSettings"]; onRefresh: Props["onRefresh"] }) {
  const settings = state.settings;
  const runtimeMode = settings?.runtime_mode ?? (settings?.offline_mode ? "offline" : "hybrid");

  return (
    <section className="panel control-panel">
      <div className="panel-heading">
        <SlidersHorizontal size={18} />
        <h2>Панель управления</h2>
      </div>
      <ToggleRow label="Голосовое пробуждение" checked={Boolean(settings?.voice_wake_enabled)} onChange={(value) => onPatchSettings({ voice_wake_enabled: value })} />
      <ToggleRow label="Хлопок" checked={Boolean(settings?.clap_enabled)} onChange={(value) => onPatchSettings({ clap_enabled: value })} />
      <ToggleRow label="Автозапуск" checked={Boolean(settings?.autostart_enabled)} onChange={(value) => onPatchSettings({ autostart_enabled: value })} />
      <label className="field-row">
        <span>Режим</span>
        <select value={runtimeMode} onChange={(event) => onPatchSettings({ runtime_mode: event.target.value as SettingsData["runtime_mode"] })}>
          <option value="hybrid">Hybrid</option>
          <option value="online">Online</option>
          <option value="offline">Offline</option>
        </select>
      </label>
      <label className="field-row">
        <span>Громкость голоса</span>
        <input type="range" min="0" max="100" value={settings?.voice_volume ?? 70} onChange={(event) => onPatchSettings({ voice_volume: Number(event.target.value) })} />
      </label>
      <label className="field-row">
        <span>Голосовой профиль</span>
        <select value={settings?.voice_profile ?? "Jarvis style"} onChange={(event) => onPatchSettings({ voice_profile: event.target.value })}>
          <option>Jarvis style</option>
          <option>System voice</option>
          <option>Text only</option>
        </select>
      </label>
      <button className="wide-button" type="button" onClick={onRefresh}>
        <Activity size={17} />
        Обновить статус
      </button>
    </section>
  );
}

function HistoryPanel({ state, compact = false }: { state: AppState; compact?: boolean }) {
  const history = compact ? state.history.slice(0, 5) : state.history;
  return (
    <div className={compact ? "history-list compact" : "history-list"}>
      {history.map((item) => (
        <article key={item.id}>
          <span>{item.time}</span>
          <strong>Пользователь: {item.userText}</strong>
          <p>JARVIS: {item.assistantText}</p>
        </article>
      ))}
      {!history.length && <p className="empty-text">Последние 5 команд появятся здесь.</p>}
    </div>
  );
}

function CommandsPanel({ state }: { state: AppState }) {
  const commands = useMemo(() => state.commands.slice(0, 36), [state.commands]);
  return (
    <section className="panel page-panel">
      <div className="panel-heading">
        <Command size={18} />
        <h2>Команды</h2>
      </div>
      <div className="command-list">
        {commands.map((command) => (
          <article key={command.id}>
            <CheckCircle2 size={17} />
            <div>
              <strong>{command.name ?? command.id}</strong>
              <p>{(command.phrases ?? command.triggers ?? []).join(", ")}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function MyCommandsPanel({ state }: { state: AppState }) {
  return (
    <section className="panel page-panel">
      <div className="panel-heading split">
        <div className="panel-heading no-margin">
          <Bot size={18} />
          <h2>Мои команды</h2>
        </div>
        <button className="small-button" type="button">
          <Plus size={16} />
          Добавить команду
        </button>
      </div>
      <div className="command-list">
        {state.commands.slice(0, 12).map((command) => (
          <article key={command.id}>
            <Command size={17} />
            <div>
              <strong>{command.name ?? command.id}</strong>
              <p>{(command.phrases ?? command.triggers ?? []).join(", ") || "Фразы не заданы"}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ScenariosPanel({
  settings,
  onChange,
  onScenario,
  savedText
}: {
  settings: LocalSettings;
  onChange: (patch: Partial<LocalSettings>) => void;
  onScenario: Props["onScenario"];
  savedText: string;
}) {
  const [active, setActive] = useState<"welcome" | "workspace" | "news">("welcome");
  return (
    <section className="panel page-panel">
      <ScenarioHeader title="Сценарии" icon={<Sparkles size={18} />} savedText={savedText} />
      <div className="scenario-tabs">
        <button className={active === "welcome" ? "active" : ""} type="button" onClick={() => setActive("welcome")}>
          <Music2 size={17} />
          Я вернулся
        </button>
        <button className={active === "workspace" ? "active" : ""} type="button" onClick={() => setActive("workspace")}>
          <FolderOpen size={17} />
          Моя рабочая среда
        </button>
        <button className={active === "news" ? "active" : ""} type="button" onClick={() => setActive("news")}>
          <Newspaper size={17} />
          Новости
        </button>
      </div>
      {active === "welcome" && <WelcomeHomeEditor settings={settings} onChange={onChange} onTest={() => onScenario("welcome-home")} />}
      {active === "workspace" && <WorkspaceEditor settings={settings} onChange={onChange} onTest={() => onScenario("workspace")} />}
      {active === "news" && <NewsEditor settings={settings} onChange={onChange} onTest={() => onScenario("news")} />}
    </section>
  );
}

function ScenarioHeader({ title, icon, savedText }: { title: string; icon: ReactNode; savedText: string }) {
  return (
    <div className="panel-heading split">
      <div className="panel-heading no-margin">
        {icon}
        <h2>{title}</h2>
      </div>
      <span className="save-state">{savedText}</span>
    </div>
  );
}

function WelcomeHomeEditor({ settings, onChange, onTest }: { settings: LocalSettings; onChange: (patch: Partial<LocalSettings>) => void; onTest: () => void }) {
  const config = settings.welcomeHome;
  const update = (patch: Partial<typeof config>) => onChange({ welcomeHome: { ...config, ...patch } });
  const chooseAudio = async () => {
    const result = await window.jarvisNative?.pickAudioFile?.();
    if (result?.path) update({ localFilePath: result.path });
  };
  return (
    <div className="form-grid">
      <TextField label="Название сценария" value={config.name} onChange={(value) => update({ name: value })} />
      <TextField label="Фразы запуска" value={config.phrases.join(", ")} onChange={(value) => update({ phrases: splitList(value) })} />
      <label className="field-row">
        <span>Music mode</span>
        <select value={config.musicMode} onChange={(event) => update({ musicMode: event.target.value as MusicMode })}>
          <option value="local_file">Local file</option>
          <option value="browser_search">Browser search</option>
          <option value="direct_url">Direct URL</option>
        </select>
      </label>
      <TextField label="Track name" value={config.trackName} onChange={(value) => update({ trackName: value })} />
      <div className="joined-field">
        <TextField label="Local file path" value={config.localFilePath} onChange={(value) => update({ localFilePath: value })} />
        <button className="icon-button" type="button" title="Выбрать mp3/wav" onClick={chooseAudio}>
          <FolderOpen size={17} />
        </button>
      </div>
      <label className="field-row">
        <span>Music provider</span>
        <select value={config.musicProvider} onChange={(event) => update({ musicProvider: event.target.value as typeof config.musicProvider })}>
          <option>KION/MTS</option>
          <option>Yandex</option>
          <option>Custom</option>
        </select>
      </label>
      <TextField label="Search URL template" value={config.searchUrlTemplate} onChange={(value) => update({ searchUrlTemplate: value })} />
      <TextField label="Direct track URL" value={config.directTrackUrl} onChange={(value) => update({ directTrackUrl: value })} />
      <ToggleRow label="Try autoplay" checked={config.tryAutoplay} onChange={(value) => update({ tryAutoplay: value })} />
      <TextField label="Fallback message" value={config.fallbackMessage} onChange={(value) => update({ fallbackMessage: value })} />
      <TextField label="Ответ Джарвиса" value={config.responseText} onChange={(value) => update({ responseText: value })} />
      <div className="form-actions">
        <button className="wide-button" type="button" onClick={onTest}>
          <Play size={17} />
          Тестировать сценарий
        </button>
        <button className="secondary-button" type="button" onClick={() => saveLocalSettings(settings)}>
          <Save size={17} />
          Сохранить
        </button>
      </div>
    </div>
  );
}

function WorkspaceEditor({ settings, onChange, onTest }: { settings: LocalSettings; onChange: (patch: Partial<LocalSettings>) => void; onTest: () => void }) {
  const config = settings.workspace;
  const update = (patch: Partial<typeof config>) => onChange({ workspace: { ...config, ...patch } });
  const addAction = (type: WorkspaceAction["type"]) => update({ actions: [...config.actions, { id: `action_${Date.now()}`, type, value: "" }] });
  const changeAction = (id: string, patch: Partial<WorkspaceAction>) => update({ actions: config.actions.map((action) => (action.id === id ? { ...action, ...patch } : action)) });
  const removeAction = (id: string) => update({ actions: config.actions.filter((action) => action.id !== id) });

  return (
    <div className="form-grid">
      <TextField label="Название сценария" value={config.name} onChange={(value) => update({ name: value })} />
      <TextField label="Фразы запуска" value={config.phrases.join(", ")} onChange={(value) => update({ phrases: splitList(value) })} />
      <ToggleRow label="Открыть ChatGPT" checked={config.openChatGPT} onChange={(value) => update({ openChatGPT: value })} />
      <TextField label="URL ChatGPT" value={config.chatgptUrl} onChange={(value) => update({ chatgptUrl: value })} />
      <ToggleRow label="Открыть VS Code" checked={config.openVSCode} onChange={(value) => update({ openVSCode: value })} />
      <TextField label="Путь к проекту" value={config.projectPath} onChange={(value) => update({ projectPath: value })} />
      <ToggleRow label="Открыть терминал" checked={config.openTerminal} onChange={(value) => update({ openTerminal: value })} />
      <TextField label="Браузерные ссылки" value={config.browserLinks.join(", ")} onChange={(value) => update({ browserLinks: splitList(value) })} />
      <TextField label="Список своих приложений" value={config.customApps.join(", ")} onChange={(value) => update({ customApps: splitList(value) })} />
      <TextField label="Список своих сайтов" value={config.customSites.join(", ")} onChange={(value) => update({ customSites: splitList(value) })} />
      <TextField label="Текст ответа Джарвиса" value={config.responseText} onChange={(value) => update({ responseText: value })} />
      <div className="action-builder">
        <div className="panel-heading no-margin">
          <Sparkles size={17} />
          <h3>Действия</h3>
        </div>
        <div className="mini-actions">
          <button type="button" onClick={() => addAction("open_url")}>
            <Link size={16} />
            Добавить сайт
          </button>
          <button type="button" onClick={() => addAction("open_app")}>
            <Command size={16} />
            Добавить приложение
          </button>
          <button type="button" onClick={() => addAction("open_folder")}>
            <FolderOpen size={16} />
            Добавить папку
          </button>
        </div>
        {config.actions.map((action) => (
          <div className="action-row" key={action.id}>
            <select value={action.type} onChange={(event) => changeAction(action.id, { type: event.target.value as WorkspaceAction["type"] })}>
              <option value="open_url">Сайт</option>
              <option value="open_app">Приложение</option>
              <option value="open_folder">Папка</option>
            </select>
            <input value={action.value} onChange={(event) => changeAction(action.id, { value: event.target.value })} placeholder="Значение" />
            <button className="icon-button danger" type="button" title="Удалить действие" onClick={() => removeAction(action.id)}>
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
      <div className="form-actions">
        <button className="wide-button" type="button" onClick={onTest}>
          <Play size={17} />
          Тестировать сценарий
        </button>
        <button className="secondary-button" type="button" onClick={() => saveLocalSettings(settings)}>
          <Save size={17} />
          Сохранить
        </button>
      </div>
    </div>
  );
}

function NewsEditor({ settings, onChange, onTest }: { settings: LocalSettings; onChange: (patch: Partial<LocalSettings>) => void; onTest: () => void }) {
  const config = settings.news;
  const update = (patch: Partial<typeof config>) => onChange({ news: { ...config, ...patch } });
  return (
    <div className="form-grid">
      <TextField label="URL новостей" value={config.newsUrl} onChange={(value) => update({ newsUrl: value })} />
      <TextField label="RSS источники" value={config.rssSources.join(", ")} onChange={(value) => update({ rssSources: splitList(value) })} />
      <label className="field-row">
        <span>Количество заголовков</span>
        <select value={config.headlineCount} onChange={(event) => update({ headlineCount: Number(event.target.value) as typeof config.headlineCount })}>
          <option value={3}>3</option>
          <option value={5}>5</option>
          <option value={10}>10</option>
        </select>
      </label>
      <ToggleRow label="Открывать браузер" checked={config.openBrowser} onChange={(value) => update({ openBrowser: value })} />
      <ToggleRow label="Читать голосом" checked={config.readAloud} onChange={(value) => update({ readAloud: value })} />
      <TextField label="Ответ Джарвиса" value={config.responseText} onChange={(value) => update({ responseText: value })} />
      <div className="form-actions">
        <button className="wide-button" type="button" onClick={onTest}>
          <Play size={17} />
          Тестировать сценарий
        </button>
        <button className="secondary-button" type="button" onClick={() => saveLocalSettings(settings)}>
          <Save size={17} />
          Сохранить
        </button>
      </div>
    </div>
  );
}

function VoicesPanel({ state, onTestMicrophone, onTestVoice }: { state: AppState; onTestMicrophone: Props["onTestMicrophone"]; onTestVoice: Props["onTestVoice"] }) {
  return (
    <section className="panel page-panel">
      <div className="panel-heading">
        <Headphones size={18} />
        <h2>Голос и микрофон</h2>
      </div>
      <div className="status-cards">
        <InfoCard label="sounddevice" value={state.voice?.sounddevice.available ? "installed" : "missing"} />
        <InfoCard label="numpy" value={state.voice?.numpy.available ? "installed" : "missing"} />
        <InfoCard label="STT" value={state.voice?.stt.provider ?? "not configured"} />
        <InfoCard label="TTS" value={state.ttsStatus?.primary ?? state.voice?.tts.mode ?? "text only"} />
        <InfoCard label="Jarvis voice" value={state.settings?.fish_audio_voice_configured ? "Fish Audio voice id" : "Fish Audio unavailable"} />
      </div>
      <button className="wide-button" type="button" onClick={onTestMicrophone}>
        <Mic size={17} />
        Проверить микрофон
      </button>
      <button className="wide-button" type="button" onClick={onTestVoice}>
        <Volume2 size={17} />
        Проверить голос
      </button>
    </section>
  );
}

function SettingsPanel({
  state,
  localSettings,
  onLocalChange,
  onPatchSettings,
  savedText
}: {
  state: AppState;
  localSettings: LocalSettings;
  onLocalChange: (patch: Partial<LocalSettings>) => void;
  onPatchSettings: Props["onPatchSettings"];
  savedText: string;
}) {
  const appearance = localSettings.appearance;
  const sounds = localSettings.sounds;
  const updateAppearance = (patch: Partial<typeof appearance>) => onLocalChange({ appearance: { ...appearance, ...patch } });
  const updateSounds = (patch: Partial<typeof sounds>) => onLocalChange({ sounds: { ...sounds, ...patch } });
  const testSound = (eventName: SoundEventName) => playSound(eventName);
  return (
    <section className="panel page-panel">
      <ScenarioHeader title="Настройки" icon={<Settings size={18} />} savedText={savedText} />
      <div className="settings-section">
        <div className="panel-heading no-margin">
          <Palette size={18} />
          <h3>Внешний вид</h3>
        </div>
        <div className="accent-grid">
          {Object.entries(accentPresets).map(([name, color]) => (
            <button
              className={appearance.accentPreset === name ? "active" : ""}
              key={name}
              type="button"
              onClick={() => updateAppearance({ accentPreset: name as typeof appearance.accentPreset, accentColor: color })}
            >
              <span style={{ "--swatch": color } as CSSProperties} />
              {accentName(name)}
            </button>
          ))}
          <button className={appearance.accentPreset === "custom" ? "active" : ""} type="button" onClick={() => updateAppearance({ accentPreset: "custom" })}>
            <span style={{ "--swatch": appearance.accentColor } as CSSProperties} />
            Custom
          </button>
        </div>
        <label className="field-row">
          <span>Accent Color</span>
          <input type="color" value={appearance.accentColor} onChange={(event) => updateAppearance({ accentPreset: "custom", accentColor: event.target.value })} />
        </label>
        <div className="theme-preview">
          <span />
          <strong>Preview</strong>
          <p>Кнопки, switches, glow и active sidebar используют выбранный цвет.</p>
        </div>
        <button className="wide-button" type="button" onClick={() => saveLocalSettings(localSettings)}>
          <Save size={17} />
          Сохранить
        </button>
      </div>
      <div className="settings-section">
        <div className="panel-heading no-margin">
          <Volume1 size={18} />
          <h3>Звуки</h3>
        </div>
        <ToggleRow label="Звуковые эффекты" checked={sounds.enabled} onChange={(value) => updateSounds({ enabled: value })} />
        <label className="field-row">
          <span>Громкость эффектов: {Math.round(sounds.volume * 100)}%</span>
          <input type="range" min="0" max="100" value={Math.round(sounds.volume * 100)} onChange={(event) => updateSounds({ volume: Number(event.target.value) / 100 })} />
        </label>
        <div className="sound-test-row">
          <button className="secondary-button" type="button" onClick={() => testSound("startup")}>
            Тест startup
          </button>
          <button className="secondary-button" type="button" onClick={() => testSound("success")}>
            Тест success
          </button>
          <button className="secondary-button" type="button" onClick={() => testSound("error")}>
            Тест error
          </button>
        </div>
      </div>
      <div className="settings-list">
        <InfoCard label="Версия" value={state.settings?.version ?? "0.1.0"} />
        <InfoCard label="Лицензия" value="Отключена" />
        <InfoCard label="OpenRouter" value={state.settings?.openrouter_configured ? "configured" : "missing"} />
        <InfoCard label="Fish Audio" value={state.settings?.fish_audio_configured ? "configured" : "missing"} />
      </div>
      <div className="settings-section" style={{ marginTop: '16px', background: 'rgba(8, 13, 22, 0.4)' }}>
        <div className="panel-heading no-margin">
          <Activity size={18} />
          <h3>Информация о сборке</h3>
        </div>
        <div className="settings-list" style={{ marginTop: '12px', marginBottom: 0 }}>
          <InfoCard label="Git Commit SHA" value={state.buildInfo?.git_sha ?? "unknown"} />
          <InfoCard label="Git Ветка" value={state.buildInfo?.git_branch ?? "unknown"} />
          <InfoCard label="Дата сборки" value={state.buildInfo?.built_at ?? "unknown"} />
          <InfoCard label="Режим Frontend" value={state.buildInfo?.frontend_mode ?? "unknown"} />
          <InfoCard label="Из исходников" value={state.buildInfo?.running_from_source ? "Да" : "Нет"} />
          <InfoCard label="Упакован (Packaged)" value={state.buildInfo?.packaged ? "Да" : "Нет"} />
          <InfoCard label="API URL" value={import.meta.env.VITE_JARVIS_API_BASE ?? "http://127.0.0.1:8000"} />
        </div>
      </div>
      <ToggleRow label="Debug details" checked={Boolean(state.settings?.debug_mode)} onChange={(value) => onPatchSettings({ debug_mode: value })} />
    </section>
  );
}

function DiagnosticsPanel({
  state,
  onDiagnostics,
  onTestMicrophone,
  onTestOpenRouter,
  onTestFishAudio,
  onTestAiFallback
}: {
  state: AppState;
  onDiagnostics: Props["onDiagnostics"];
  onTestMicrophone: Props["onTestMicrophone"];
  onTestOpenRouter: Props["onTestOpenRouter"];
  onTestFishAudio: Props["onTestFishAudio"];
  onTestAiFallback: Props["onTestAiFallback"];
}) {
  const openLogs = () => window.jarvisNative?.openLogs?.();
  const openrouterError = state.openrouterTest && !state.openrouterTest.ok ? state.openrouterTest.error_message ?? state.openrouterTest.fix ?? "error" : "none";
  const fishError = state.fishAudioTest && !state.fishAudioTest.ok ? state.fishAudioTest.error_message ?? state.fishAudioTest.fix ?? "error" : "none";
  const aiError = state.aiFallbackTest?.route === "ai_fallback" && state.aiFallbackTest.status !== "completed" ? state.aiFallbackTest.text ?? state.aiFallbackTest.response_text : "none";
  return (
    <section className="panel page-panel">
      <div className="panel-heading">
        <Wrench size={18} />
        <h2>Диагностика</h2>
      </div>
      <div className="diagnostic-actions">
        <button type="button" onClick={onTestOpenRouter}>Проверить OpenRouter</button>
        <button type="button" onClick={onTestFishAudio}>Проверить Fish Audio</button>
        <button type="button" onClick={onTestAiFallback}>Проверить полный pipeline</button>
        <button type="button" onClick={onDiagnostics}>Полная проверка</button>
        <button type="button" onClick={onTestMicrophone}>Микрофон</button>
        <button type="button" onClick={openLogs}>Открыть папку логов</button>
      </div>
      <div className="checks-grid">
        <InfoCard label="OpenRouter key" value={state.debugEnv?.openrouter.key_present ? "present" : "missing"} />
        <InfoCard label="OpenRouter model" value={state.debugEnv?.openrouter.model ?? "unknown"} />
        <InfoCard label="OpenRouter status" value={state.openrouterTest ? (state.openrouterTest.ok ? "ok" : "failed") : "not tested"} />
        <InfoCard label="OpenRouter latency" value={state.openrouterTest?.latency_ms ? `${state.openrouterTest.latency_ms} ms` : "n/a"} />
        <InfoCard label="OpenRouter last error" value={openrouterError} />
        <InfoCard label="Fish Audio key" value={state.debugEnv?.fish_audio.key_present ? "present" : "missing"} />
        <InfoCard label="Fish voice id" value={state.debugEnv?.fish_audio.voice_id_present ? "present" : "missing"} />
        <InfoCard label="Fish status" value={state.fishAudioTest ? (state.fishAudioTest.ok ? "ok" : "failed") : "not tested"} />
        <InfoCard label="Fish latency" value={state.fishAudioTest?.latency_ms ? `${state.fishAudioTest.latency_ms} ms` : "n/a"} />
        <InfoCard label="Fish last error" value={fishError} />
        <InfoCard label="TTS primary" value={state.ttsStatus?.primary ?? state.debugEnv?.tts?.primary ?? "fish_audio"} />
        <InfoCard label="Require Fish Audio" value={String(state.ttsStatus?.require_fish_audio ?? state.debugEnv?.tts?.require_fish_audio ?? true)} />
        <InfoCard label="Fallback enabled" value={String(state.ttsStatus?.fallback_enabled ?? state.debugEnv?.tts?.fallback_enabled ?? false)} />
        <InfoCard label="Last TTS provider" value={state.ttsStatus?.last_provider_used ?? "none"} />
        <InfoCard label="Last TTS error" value={state.ttsStatus?.last_error ?? "none"} />
        <InfoCard label="Pipeline route" value={state.aiFallbackTest?.route ?? state.lastResult?.route ?? "none"} />
        <InfoCard label="Pipeline provider" value={state.aiFallbackTest?.provider ?? state.lastResult?.provider ?? "none"} />
        <InfoCard label="Pipeline TTS" value={state.aiFallbackTest?.tts?.provider ?? state.lastResult?.tts?.provider ?? "none"} />
        <InfoCard label="Pipeline error" value={aiError} />
      </div>
      <div className="checks-grid">
        {Object.entries(state.diagnostics?.checks ?? {}).map(([key, value]) => (
          <InfoCard key={key} label={key} value={value} />
        ))}
      </div>
    </section>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="field-row">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <i />
    </label>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function accentName(name: string): string {
  const names: Record<string, string> = {
    blue: "Blue",
    purple: "Purple",
    cyan: "Cyan",
    green: "Green",
    red: "Red",
    orange: "Orange"
  };
  return names[name] ?? name;
}
