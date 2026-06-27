import { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { useSessionMessages } from '@/hooks/use-sessions';
import { EvoGenWS } from '@/lib/ws';
import { cn, generateId } from '@/lib/utils';
import { useQueryClient } from '@tanstack/react-query';
import { useChatContext } from '@/context/chat-context';
import { useWsStatus } from '@/context/ws-context';
import { MessageBubble } from '@/components/chat/message-bubble';
import { ChatInput } from '@/components/chat/chat-input';
import { WelcomeEmpty } from '@/components/chat/welcome-empty';
import type { ChatMsg, WsAgentEvent } from '@/types';

export function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeId = searchParams.get('session') || '';
  const [input, setInput] = useState('');
  const { wsStatus, setWsStatus } = useWsStatus();
  const wsRef = useRef<EvoGenWS | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingSessionRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const [streamingUi, setStreamingUi] = useState(false);
  const qc = useQueryClient();
  const { state: chat, setMessages, setStreaming, setActiveSession, updateLastAssistant, finalizeLastAssistant, clearMessages, setReasoning } = useChatContext();

  const { data: msgData, isLoading: msgsLoading } = useSessionMessages(activeId);

  // Sync active session ID to context (don't clear on empty — preserve across nav)
  useEffect(() => {
    if (activeId) setActiveSession(activeId);
  }, [activeId, setActiveSession]);

  // Load messages from backend when session changes
  useEffect(() => {
    if (msgData?.messages) {
      setMessages(msgData.messages.map((m) => ({
        id: String(m.id),
        role: m.role as ChatMsg['role'],
        content: m.content,
        timestamp: m.timestamp,
      })));
    } else if (activeId && !msgsLoading) {
      setMessages([]);
    }
  }, [msgData, activeId, msgsLoading, setMessages]);

  useEffect(() => {
    const ws = new EvoGenWS(
      `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/ws`,
    );
    wsRef.current = ws;
    ws.onStatus(setWsStatus);

    // WebSocket fallback
    ws.onMessage((evt: WsAgentEvent) => {
      const { chunk, status } = evt.payload;
      if (chunk) {
        updateLastAssistant(chunk, 'streaming-');
      }
      if (status === 'complete') {
        streamingRef.current = false;
        setStreamingUi(false);
        setStreaming(false);
        finalizeLastAssistant();
        if (activeId) {
          qc.invalidateQueries({ queryKey: ['sessions', activeId, 'messages'] });
          qc.invalidateQueries({ queryKey: ['sessions'] });
        }
      }
    });
    ws.connect();
    return () => { ws.disconnect(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat.messages]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || streamingRef.current) return;
    const userMsg: ChatMsg = { id: generateId(), role: 'user', content: text, timestamp: new Date().toISOString() };
    const currentMsgs = chat.messages;
    setMessages([...currentMsgs, userMsg]);
    setInput('');
    streamingRef.current = true;
    setStreamingUi(true);

    // Fire-and-forget async SSE — state updates via stable refs
    const effectiveSession = activeId || chat.activeSessionId;
    sendMessageAndStream(text, effectiveSession).finally(() => {
      streamingRef.current = false;
      setTimeout(() => {
        setStreamingUi(false);
      }, 800);
      qc.invalidateQueries({ queryKey: ['sessions'] });
      if (activeId) {
        qc.invalidateQueries({ queryKey: ['sessions', activeId, 'messages'] });
      }
    });
  }, [input, activeId, chat.messages, setMessages, qc]);

  // Stable refs for async callbacks
  const updateLastAssistantRef = useRef(updateLastAssistant);
  updateLastAssistantRef.current = updateLastAssistant;
  const finalizeLastAssistantRef = useRef(finalizeLastAssistant);
  finalizeLastAssistantRef.current = finalizeLastAssistant;
  const setReasoningRef = useRef(setReasoning);
  setReasoningRef.current = setReasoning;
  const setSearchParamsRef = useRef(setSearchParams);
  setSearchParamsRef.current = setSearchParams;

  const sendMessageAndStream = useCallback(async (text: string, activeId: string) => {
    const B = window.location.origin;
    const token = (() => { try { return localStorage.getItem('evogen-auth-token') || ''; } catch { return ''; } })();
    const H: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    };
    const body: Record<string, unknown> = { message: text };
    if (activeId) body.session = activeId;

    try {
      const res = await fetch(`${B}/api/v1/agent/chat`, { method: 'POST', headers: H, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') break;
          try {
            const parsed = JSON.parse(data);
            if (parsed.session && !activeId) {
              pendingSessionRef.current = parsed.session;
            }
            // ── 处理普通 chunk ──
            if (parsed.chunk) {
              updateLastAssistantRef.current(parsed.chunk, 'sse-');
            }
            // ── 处理 reasoning（R1 模型思考过程）──
            if (parsed.status === 'reasoning' && parsed.content) {
              setReasoningRef.current(parsed.content);
            }
          } catch {
            if (data) updateLastAssistantRef.current(data, 'sse-');
          }
        }
      }
    } catch (err) {
      console.warn('SSE stream error:', err);
    }

    finalizeLastAssistantRef.current();
    if (pendingSessionRef.current) {
      setSearchParamsRef.current({ session: pendingSessionRef.current });
      pendingSessionRef.current = null;
    }
  }, []);

  const newChat = () => {
    setSearchParams({});
    clearMessages();
  };

  // Stop streaming: abort the fetch + cancel streaming state
  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    streamingRef.current = false;
    setStreamingUi(false);
    setStreaming(false);
    finalizeLastAssistant();
  }, [finalizeLastAssistant, setStreaming]);

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--color-bg-deep)' }}>
      {/* ── Top bar ───────────────────────────────────────────── */}
      <header
        className="h-14 md:h-16 flex items-center justify-between relative z-50 p-4 md:px-6 flex-shrink-0"
        style={{
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid var(--color-border-glass)',
        }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <h1 className="text-[15px] font-semibold text-primary truncate">
            {activeId ? (msgData?.messages?.[0]?.content?.slice(0, 40) || '对话') : '对话'}
          </h1>
          <span
            className={cn(
              'text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider flex items-center gap-1.5',
            )}
            style={{
              color: wsStatus === 'connected' ? 'var(--color-mint)' :
                wsStatus === 'connecting' ? 'var(--color-warning)' : 'var(--color-text-muted)',
              background: wsStatus === 'connected' ? 'rgba(0,255,136,0.08)' :
                wsStatus === 'connecting' ? 'rgba(255,170,51,0.08)' : 'rgba(100,100,200,0.06)',
            }}
          >
            <span className={cn('w-1.5 h-1.5 rounded-full')}
              style={{
                background: wsStatus === 'connected' ? 'var(--color-mint)' :
                  wsStatus === 'connecting' ? 'var(--color-warning)' : 'var(--color-text-muted)',
              }}
            />
            {wsStatus === 'connected' ? 'LIVE' : wsStatus === 'connecting' ? 'SYNC' : 'OFF'}
          </span>
        </div>
        <button
          className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-lg transition-all text-secondary hover:text-primary hover:bg-hover"
          onClick={newChat}
        >
          <Plus style={{ width: 14, height: 14 }} />
          新对话
        </button>
      </header>

      {/* ── Content ────────────────────────────────────────────── */}
      <main className="flex flex-col flex-1">
        {/* ── Empty state or messages ────────────────────────── */}
        {!activeId && chat.messages.length === 0 ? (
          <WelcomeEmpty onSuggestionClick={(text) => setInput(text)} />
        ) : (
          <section className="flex flex-col flex-1 pt-2 md:pt-4 px-4 md:px-6 pb-4 max-w-3xl mx-auto w-full">
            <div className="flex-1 space-y-4">
              {msgsLoading ? (
                <div className="space-y-4">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="flex gap-3">
                      <div className="w-7 h-7 rounded-lg skeleton flex-shrink-0" />
                      <div className="space-y-2 flex-1">
                        <div className="skeleton h-4 w-2/3" />
                        <div className="skeleton h-4 w-1/2" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                chat.messages.map((msg) => {
                  const isStreaming = msg.id.startsWith('streaming-') || msg.id.startsWith('sse-');
                  return (
                    <MessageBubble
                      key={msg.id}
                      role={msg.role as 'user' | 'assistant' | 'tool'}
                      content={msg.content}
                      timestamp={msg.timestamp}
                      isStreaming={isStreaming}
                      reasoning={msg.reasoning}
                    />
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>
          </section>
        )}

        {/* ── Chat Input ─────────────────────────────────────── */}
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={handleStop}
          disabled={msgsLoading}
          streaming={streamingUi}
        />
      </main>
    </div>
  );
}
