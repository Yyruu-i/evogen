/* ═══════════════════════════════════════════════════════════
   EvoGen — WebSocket manager
   Auto-reconnect, auto-auth, event dispatch.
   ═══════════════════════════════════════════════════════════ */

import type { WsAgentEvent } from '@/types';

type MessageHandler = (event: WsAgentEvent) => void;
type StatusHandler = (status: 'connecting' | 'connected' | 'disconnected') => void;

export class EvoGenWS {
  private ws: WebSocket | null = null;
  private token: string;
  private url: string;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private messageHandlers = new Set<MessageHandler>();
  private statusHandlers = new Set<StatusHandler>();
  private shouldReconnect = false;

  constructor(url: string, token: string) {
    this.url = url;
    this.token = token;
  }

  onMessage(handler: MessageHandler) {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onStatus(handler: StatusHandler) {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.shouldReconnect = true;
    this.emitStatus('connecting');
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.emitStatus('connected');
      // Send connect frame
      this.send({
        type: 'req',
        method: 'connect',
        params: {
          deviceId: `web-${crypto.randomUUID().slice(0, 8)}`,
          deviceName: 'EvoGen Web',
          platform: 'web',
          auth: { token: this.token },
          role: 'client',
        },
      });
    };

    this.ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'event' && data.event === 'agent') {
          for (const h of this.messageHandlers) h(data as WsAgentEvent);
        }
      } catch {
        // ignore non-JSON frames
      }
    };

    this.ws.onclose = () => {
      this.emitStatus('disconnected');
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose will fire next
    };
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  send(data: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  sendMessage(message: string, sessionId?: string) {
    this.send({
      type: 'req',
      method: 'agent',
      params: {
        message,
        session: sessionId || undefined,
      },
    });
  }

  private scheduleReconnect() {
    if (!this.shouldReconnect) return;
    this.reconnectTimer = setTimeout(() => this.connect(), 3000);
  }

  private emitStatus(status: 'connecting' | 'connected' | 'disconnected') {
    for (const h of this.statusHandlers) h(status);
  }
}
