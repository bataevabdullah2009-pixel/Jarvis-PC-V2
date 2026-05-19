const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const BACKEND_PORT = process.env.JARVIS_BACKEND_PORT || "8000";
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev = Boolean(process.env.JARVIS_FRONTEND_URL) || Boolean(process.defaultApp);

let backendProcess = null;

function projectRoot() {
  return path.resolve(__dirname, "..", "..");
}

function logDirectory() {
  const root = isDev ? projectRoot() : path.dirname(process.execPath);
  return path.join(root, "logs");
}

function ensureLogDirectory() {
  const directory = logDirectory();
  try {
    fs.mkdirSync(directory, { recursive: true });
    return directory;
  } catch {
    const fallback = path.join(app.getPath("userData"), "logs");
    fs.mkdirSync(fallback, { recursive: true });
    return fallback;
  }
}

function writeLog(name, message) {
  try {
    const directory = ensureLogDirectory();
    const line = `${new Date().toISOString()} ${message}\n`;
    fs.appendFileSync(path.join(directory, name), line, "utf-8");
  } catch {
    try {
      const fallback = path.join(app.getPath("userData"), "logs");
      fs.mkdirSync(fallback, { recursive: true });
      const line = `${new Date().toISOString()} ${message}\n`;
      fs.appendFileSync(path.join(fallback, name), line, "utf-8");
    } catch {
      // Logging must never block startup.
    }
  }
}

function writeElectronLog(message) {
  writeLog("electron.log", message);
}

function writeFrontendLog(message) {
  writeLog("frontend.log", message);
}

function writeBackendLog(message) {
  writeLog("backend.log", message);
}

function backendResourceRoot() {
  if (isDev) {
    return path.resolve(projectRoot(), "backend");
  }
  return path.join(process.resourcesPath, "backend");
}

function assertBackendPackage(root) {
  const exePath = path.join(root, "JarvisBackend.exe");
  const scriptPath = path.join(root, "run_backend.py");
  if (!fs.existsSync(exePath) && !fs.existsSync(scriptPath)) {
    throw new Error(
      `Backend package не найден: ${root}. Запустите tools\\build_backend_exe.bat или npm run prepare:backend.`
    );
  }
}

function findBackendCommand() {
  const root = backendResourceRoot();
  assertBackendPackage(root);

  const exePath = path.join(root, "JarvisBackend.exe");
  const scriptPath = path.join(root, "run_backend.py");

  if (fs.existsSync(exePath)) {
    writeElectronLog(`backend command exe=${exePath}`);
    return { command: exePath, args: [], cwd: root };
  }

  writeElectronLog(`backend command python script=${scriptPath}`);
  return { command: process.env.JARVIS_PYTHON || "python", args: [scriptPath], cwd: root };
}

function pipeBackendLogs(processHandle) {
  if (processHandle.stdout) {
    processHandle.stdout.on("data", (chunk) => writeBackendLog(chunk.toString("utf-8").trimEnd()));
  }
  if (processHandle.stderr) {
    processHandle.stderr.on("data", (chunk) => writeBackendLog(chunk.toString("utf-8").trimEnd()));
  }
}

function startBackend() {
  const healthUrl = `${BACKEND_URL}/health`;
  writeElectronLog(`checking backend health ${healthUrl}`);
  return fetch(healthUrl, { signal: AbortSignal.timeout(800) })
    .then(() => {
      writeElectronLog("backend already healthy");
      return true;
    })
    .catch(() => {
      const backend = findBackendCommand();
      writeElectronLog(`spawning backend command=${backend.command} cwd=${backend.cwd}`);
      backendProcess = spawn(backend.command, backend.args, {
        cwd: backend.cwd,
        env: {
          ...process.env,
          JARVIS_BACKEND_PORT: BACKEND_PORT,
          JARVIS_BACKEND_HOST: "127.0.0.1",
          LICENSE_ENABLED: "false"
        },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"]
      });

      writeElectronLog(`backend process pid=${backendProcess.pid}`);
      pipeBackendLogs(backendProcess);

      backendProcess.on("exit", (code, signal) => {
        writeElectronLog(`backend process exited code=${code} signal=${signal}`);
        backendProcess = null;
      });

      backendProcess.on("error", (error) => {
        writeElectronLog(`backend process error=${error instanceof Error ? error.message : String(error)}`);
      });

      return waitForBackend(healthUrl);
    });
}

async function waitForBackend(healthUrl) {
  const started = Date.now();
  while (Date.now() - started < 20000) {
    try {
      const response = await fetch(healthUrl, { signal: AbortSignal.timeout(1000) });
      if (response.ok) {
        writeElectronLog(`backend health check ok status=${response.status}`);
        return true;
      }
      writeElectronLog(`backend health check not ready status=${response.status}`);
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 600));
    }
  }
  throw new Error("Backend не запустился за 20 секунд.");
}

function stopBackend() {
  if (backendProcess) {
    try {
      writeElectronLog(`stopping backend pid=${backendProcess.pid}`);
      backendProcess.kill();
    } catch (error) {
      writeElectronLog(`backend kill failed=${error instanceof Error ? error.message : String(error)}`);
    }
    backendProcess = null;
  }
}

function fallbackHtml(errorMessage) {
  const safeMessage = String(errorMessage).replace(/[<>&]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[char]);
  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>JARVIS UI не загрузился</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #090d14; color: #e8eef8; font-family: Segoe UI, Arial, sans-serif; }
    section { width: min(620px, calc(100vw - 32px)); border: 1px solid #243246; border-radius: 8px; padding: 28px; background: #101724; box-shadow: 0 0 42px rgba(83, 116, 255, 0.14); }
    h1 { margin: 0 0 12px; font-size: 28px; }
    p { color: #aebbd0; line-height: 1.55; }
    pre { overflow: auto; max-height: 180px; padding: 12px; border-radius: 8px; background: #070b11; color: #ffd166; white-space: pre-wrap; }
    button { height: 42px; border: 0; border-radius: 8px; padding: 0 16px; background: #355cff; color: white; font: inherit; font-weight: 700; cursor: pointer; }
  </style>
</head>
<body>
  <section>
    <h1>JARVIS UI не загрузился</h1>
    <p>Интерфейс не смог открыть production bundle. Подробности записаны в logs/electron.log и logs/frontend.log.</p>
    <pre>${safeMessage}</pre>
    <button onclick="window.jarvisNative && window.jarvisNative.openLogs()">Открыть логи</button>
  </section>
</body>
</html>`;
}

async function showFallback(window, error) {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  writeFrontendLog(`fallback shown: ${message}`);
  await window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(fallbackHtml(message))}`);
  window.show();
}

async function createWindow() {
  writeElectronLog(`app started mode=${isDev ? "dev" : "packaged"} packaged=${app.isPackaged} resources=${process.resourcesPath}`);
  await startBackend();

  const window = new BrowserWindow({
    width: 1060,
    height: 720,
    minWidth: 920,
    minHeight: 620,
    backgroundColor: "#090d14",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.cjs"),
      devTools: true
    }
  });

  window.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    writeFrontendLog(`console level=${level} source=${sourceId}:${line} ${message}`);
  });

  window.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    if (String(validatedURL || "").startsWith("data:")) {
      return;
    }
    writeElectronLog(`did-fail-load code=${errorCode} description=${errorDescription} url=${validatedURL}`);
    showFallback(window, `${errorDescription} (${errorCode}) while loading ${validatedURL}`).catch((error) => {
      writeElectronLog(`fallback failed=${error instanceof Error ? error.stack || error.message : String(error)}`);
    });
  });

  window.once("ready-to-show", () => {
    window.show();
  });

  try {
    if (isDev) {
      const url = process.env.JARVIS_FRONTEND_URL || "http://127.0.0.1:5173";
      writeElectronLog(`loading dev frontend url=${url}`);
      try {
        await window.loadURL(url);
      } catch (error) {
        const indexPath = path.join(__dirname, "..", "dist", "index.html");
        if (!fs.existsSync(indexPath)) {
          throw error;
        }
        writeElectronLog(`dev frontend unavailable, loading built frontend file=${indexPath}`);
        await window.loadFile(indexPath);
      }
    } else {
      const indexPath = path.join(__dirname, "..", "dist", "index.html");
      if (!fs.existsSync(indexPath)) {
        throw new Error(`Frontend build не найден: ${indexPath}. Сначала выполните npm run build.`);
      }
      writeElectronLog(`loading frontend file=${indexPath}`);
      await window.loadFile(indexPath);
    }
  } catch (error) {
    await showFallback(window, error);
  }
}

async function showStartupErrorDialog(error) {
  const detail = error instanceof Error ? error.stack || error.message : String(error);
  writeElectronLog(`startup error=${detail}`);
  const result = await dialog.showMessageBox({
    type: "error",
    title: "JARVIS PC V2",
    message: "Backend не запустился",
    detail: `${detail}\n\nЛоги: ${ensureLogDirectory()}`,
    buttons: ["Повторить", "Открыть логи", "Закрыть"],
    defaultId: 0,
    cancelId: 2,
    noLink: true
  });
  if (result.response === 1) {
    await shell.openPath(ensureLogDirectory());
  }
  return result.response;
}

async function launchWithRetry() {
  while (true) {
    try {
      await createWindow();
      return;
    } catch (error) {
      stopBackend();
      const response = await showStartupErrorDialog(error);
      if (response === 0 || response === 1) {
        continue;
      }
      app.quit();
      return;
    }
  }
}

if (ipcMain && typeof ipcMain.handle === "function") {
  ipcMain.handle("jarvis:open-logs", async () => {
    const directory = ensureLogDirectory();
    await shell.openPath(directory);
  });

  ipcMain.handle("jarvis:open-path", async (_event, targetPath) => {
    try {
      const message = await shell.openPath(String(targetPath || ""));
      return message ? { ok: false, message } : { ok: true };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : String(error) };
    }
  });

  ipcMain.handle("jarvis:open-url", async (_event, url) => {
    try {
      await shell.openExternal(String(url || ""));
      return { ok: true };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : String(error) };
    }
  });

  ipcMain.handle("jarvis:open-command", async (_event, command, args = []) => {
    try {
      const child = spawn(String(command || ""), Array.isArray(args) ? args.map(String) : [], {
        detached: true,
        stdio: "ignore",
        windowsHide: true
      });
      child.unref();
      return { ok: true };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : String(error) };
    }
  });

  ipcMain.handle("jarvis:pick-audio-file", async () => {
    const result = await dialog.showOpenDialog({
      title: "Выберите аудиофайл",
      properties: ["openFile"],
      filters: [{ name: "Audio", extensions: ["mp3", "wav", "flac", "m4a", "aac", "ogg"] }]
    });
    return { canceled: result.canceled, path: result.filePaths[0] };
  });

  ipcMain.handle("jarvis:media-play-pause", async () => {
    try {
      spawn("powershell", [
        "-NoProfile",
        "-WindowStyle",
        "Hidden",
        "-Command",
        "$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys([char]179)"
      ], { windowsHide: true, stdio: "ignore" });
      return { ok: true };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : String(error) };
    }
  });
} else {
  writeElectronLog("ipcMain is unavailable; open logs button will only log renderer errors.");
}

process.on("uncaughtException", (error) => {
  writeElectronLog(`uncaughtException=${error instanceof Error ? error.stack || error.message : String(error)}`);
});

process.on("unhandledRejection", (error) => {
  writeElectronLog(`unhandledRejection=${error instanceof Error ? error.stack || error.message : String(error)}`);
});

app.whenReady().then(launchWithRetry).catch((error) => {
  writeElectronLog(`startup error=${error instanceof Error ? error.stack || error.message : String(error)}`);
  dialog.showErrorBox("JARVIS PC V2", error instanceof Error ? error.message : String(error));
  app.quit();
});

app.on("before-quit", () => {
  stopBackend();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    launchWithRetry();
  }
});
