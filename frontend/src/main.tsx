import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./screens/App";
import "./styles/app.css";

type ErrorFallbackProps = {
  error?: unknown;
};

function logFrontendError(error: unknown) {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  console.error("[JARVIS_UI_ERROR]", message);
  window.dispatchEvent(new CustomEvent("jarvis-ui-error", { detail: { message } }));
}

class ErrorBoundary extends React.Component<React.PropsWithChildren, { error: unknown | null }> {
  constructor(props: React.PropsWithChildren) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  componentDidCatch(error: unknown) {
    logFrontendError(error);
  }

  render() {
    if (this.state.error) {
      return <ErrorFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}

function ErrorFallback({ error }: ErrorFallbackProps) {
  const details = error instanceof Error ? error.message : String(error ?? "Unknown renderer error");
  const openLogs = () => {
    window.jarvisNative?.openLogs?.();
    window.dispatchEvent(new CustomEvent("jarvis-open-logs"));
  };

  return (
    <main className="ui-error-screen">
      <section>
        <p className="eyebrow">renderer fallback</p>
        <h1>JARVIS UI не загрузился</h1>
        <p>React остановился до отображения интерфейса. Ошибка записана в логи Electron.</p>
        <pre>{details}</pre>
        <button type="button" onClick={openLogs}>
          Открыть логи
        </button>
      </section>
    </main>
  );
}

window.addEventListener("error", (event) => logFrontendError(event.error ?? event.message));
window.addEventListener("unhandledrejection", (event) => logFrontendError(event.reason));

const root = document.getElementById("root");

if (!root) {
  logFrontendError("Root element #root not found");
  document.body.innerHTML = '<main class="ui-error-screen"><section><h1>JARVIS UI не загрузился</h1><p>#root не найден в index.html.</p></section></main>';
} else {
  createRoot(root).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>
  );
}
