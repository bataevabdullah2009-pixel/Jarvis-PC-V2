import { ArrowLeft, Activity, Mic, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { DiagnosticsData } from "../api/client";
import { AppState } from "./App";

type Props = {
  state: AppState;
  onBack: () => void;
  onLoadDiagnostics: () => Promise<DiagnosticsData | null>;
  onTestMicrophone: () => Promise<void>;
};

export function Diagnostics({ state, onBack, onLoadDiagnostics, onTestMicrophone }: Props) {
  const [diagnostics, setDiagnostics] = useState<DiagnosticsData | null>(null);

  const refresh = async () => {
    setDiagnostics(await onLoadDiagnostics());
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <main className="sub-screen">
      <header className="sub-header">
        <button className="icon-button" type="button" onClick={onBack} title="Назад">
          <ArrowLeft size={19} />
        </button>
        <div>
          <p className="eyebrow">system checks</p>
          <h1>Диагностика</h1>
        </div>
        <div className="top-actions">
          <button className="icon-button" type="button" onClick={refresh} title="Обновить">
            <RefreshCw size={18} />
          </button>
          <button className="icon-button" type="button" onClick={onTestMicrophone} title="Микрофон">
            <Mic size={18} />
          </button>
        </div>
      </header>

      <section className="diagnostics-grid">
        {Object.entries(diagnostics?.checks ?? {}).map(([key, value]) => (
          <div className="check-row" key={key}>
            <Activity size={16} />
            <span>{key}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="details-panel">
        <div>
          <span>Устройства</span>
          <strong>{state.devices.length}</strong>
        </div>
        <div>
          <span>STT</span>
          <strong>{state.voice?.stt.provider ?? "not configured"}</strong>
        </div>
        <div>
          <span>TTS</span>
          <strong>{state.voice?.tts.mode ?? "unknown"}</strong>
        </div>
        <div>
          <span>Последний статус</span>
          <strong>{state.statusText}</strong>
        </div>
      </section>

      {state.debugMode && (
        <pre className="debug-json">{JSON.stringify({ diagnostics, voice: state.voice, health: state.health }, null, 2)}</pre>
      )}
    </main>
  );
}

