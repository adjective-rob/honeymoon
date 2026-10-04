// WebSocket connection to the Honeymoon daemon

type Listener<T = unknown> = (data: T) => void;

class HoneymoonSocket {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<Listener>> = new Map();
  private reconnectTimer: NodeJS.Timeout | null = null;
  private url: string;

  constructor(url: string = "ws://127.0.0.1:4200") {
    this.url = url;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.emit("connected", {});
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const type = data.type || data.event_type || "event";
        this.emit(type, data);
        this.emit("*", data); // wildcard
      } catch {}
    };

    this.ws.onclose = () => {
      this.emit("disconnected", {});
      // Reconnect after 2s
      this.reconnectTimer = setTimeout(() => this.connect(), 2000);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  // The daemon's messages are untyped JSON; callers declare the shape they expect per event.
  on<T = unknown>(event: string, listener: Listener<T>) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener as Listener);
    return () => this.listeners.get(event)?.delete(listener as Listener);
  }

  private emit(event: string, data: unknown) {
    this.listeners.get(event)?.forEach((fn) => fn(data));
  }

  send(action: string, options: Record<string, unknown> = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, options }));
    }
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const socket = new HoneymoonSocket();
export type { Listener };
