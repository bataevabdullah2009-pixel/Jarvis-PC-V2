import { EventPayload, WS_EVENTS_URL } from "./client";

export function connectEvents(onEvent: (event: EventPayload) => void, onState?: (state: "open" | "closed" | "error") => void) {
  const socket = new WebSocket(WS_EVENTS_URL);

  socket.addEventListener("open", () => {
    onState?.("open");
  });

  socket.addEventListener("message", (message) => {
    try {
      const event = JSON.parse(message.data) as EventPayload;
      onEvent(event);
    } catch {
      onEvent({ type: "events.parse_error", payload: { raw: String(message.data) } });
    }
  });

  socket.addEventListener("error", () => {
    onState?.("error");
  });

  socket.addEventListener("close", () => {
    onState?.("closed");
  });

  return () => socket.close();
}

