const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisNative", {
  openLogs: () => ipcRenderer.invoke("jarvis:open-logs"),
  openPath: (targetPath) => ipcRenderer.invoke("jarvis:open-path", targetPath),
  openUrl: (url) => ipcRenderer.invoke("jarvis:open-url", url),
  openCommand: (command, args = []) => ipcRenderer.invoke("jarvis:open-command", command, args),
  pickAudioFile: () => ipcRenderer.invoke("jarvis:pick-audio-file"),
  mediaPlayPause: () => ipcRenderer.invoke("jarvis:media-play-pause")
});
