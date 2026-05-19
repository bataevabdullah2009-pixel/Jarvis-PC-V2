import { ArrowLeft, RefreshCw } from "lucide-react";
import { AppState } from "./App";
import { StatusPill } from "../components/StatusPill";

type Props = {
  state: AppState;
  onBack: () => void;
  onRefresh: () => Promise<void>;
};

export function Settings({ state, onBack, onRefresh }: Props) {
  return (
    <main className="sub-screen">
      <header className="sub-header">
        <button className="icon-button" type="button" onClick={onBack} title="Назад">
          <ArrowLeft size={19} />
        </button>
        <div>
          <p className="eyebrow">configuration</p>
          <h1>Настройки</h1>
        </div>
        <button className="icon-button" type="button" onClick={onRefresh} title="Обновить">
          <RefreshCw size={18} />
        </button>
      </header>

      <section className="settings-grid">
        <StatusPill label="OpenRouter" value={state.settings?.openrouter_configured ? "configured" : "missing"} tone={state.settings?.openrouter_configured ? "good" : "warn"} />
        <StatusPill label="Fish Audio" value={state.settings?.fish_audio_configured ? "configured" : "missing"} tone={state.settings?.fish_audio_configured ? "good" : "warn"} />
        <StatusPill label="Voice ID" value={state.settings?.fish_audio_voice_configured ? "configured" : "missing"} tone={state.settings?.fish_audio_voice_configured ? "good" : "warn"} />
        <StatusPill label="Debug" value={state.settings?.debug_mode ? "on" : "off"} tone="idle" />
      </section>

      <section className="details-panel">
        <div>
          <span>Голос</span>
          <strong>{state.settings?.voice_profile ?? "Jarvis style"}</strong>
        </div>
        <div>
          <span>Проект</span>
          <strong>{state.settings?.workspace_project_path ?? "не задан"}</strong>
        </div>
        <div>
          <span>ChatGPT</span>
          <strong>{state.settings?.chatgpt_url ?? "не задан"}</strong>
        </div>
        <div>
          <span>Новости</span>
          <strong>{state.settings?.news_url ?? "не задан"}</strong>
        </div>
      </section>
    </main>
  );
}

