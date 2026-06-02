import { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Send, Bot, User, MessageSquare, Plus, Sparkles, ChevronDown, ChevronRight, Brain } from 'lucide-react';
import { useSessionMessages } from '@/hooks/use-sessions';
import { EvoGenWS } from '@/lib/ws';
import { formatTime, cn, generateId } from '@/lib/utils';
import { useQueryClient } from '@tanstack/react-query';
import { useChatContext } from '@/context/chat-context';
import type { ChatMsg, WsAgentEvent } from '@/types';

const DEFAULT_TOKEN = 'gateway-secret-token-change-me';

export function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeId = searchParams.get('session') || '';
  const [input, setInput] = useState('');
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const wsRef = useRef<EvoGenWS | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingSessionRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const [streamingUi, setStreamingUi] = useState(false);
  const [thinkingExpanded, setThinkingExpanded] = useState(true);
  const thinkingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const qc = useQueryClient();
  const { state: chat, setMessages, setStreaming, setActiveSession, updateLastAssistant, finalizeLastAssistant, clearMessages } = useChatContext();

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
      `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`,
      DEFAULT_TOKEN,
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

  // Cleanup thinking timer on unmount
  useEffect(() => {
    return () => { if (thinkingTimerRef.current) clearTimeout(thinkingTimerRef.current); };
  }, []);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || streamingRef.current) return;
    const userMsg: ChatMsg = { id: generateId(), role: 'user', content: text, timestamp: new Date().toISOString() };
    const currentMsgs = chat.messages;
    setMessages([...currentMsgs, userMsg]);
    setInput('');
    streamingRef.current = true;
    setStreamingUi(true);
    setThinkingExpanded(true);
    if (thinkingTimerRef.current) clearTimeout(thinkingTimerRef.current);

    // Fire-and-forget async SSE — state updates via stable refs
    const effectiveSession = activeId || chat.activeSessionId;
    sendMessageAndStream(text, effectiveSession).finally(() => {
      streamingRef.current = false;
      // Keep streaming UI visible for minimum 800ms so thinking bar renders
      setTimeout(() => {
        setStreamingUi(false);
        // Auto-collapse thinking after 1.5s
        thinkingTimerRef.current = setTimeout(() => setThinkingExpanded(false), 1500);
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
  const setSearchParamsRef = useRef(setSearchParams);
  setSearchParamsRef.current = setSearchParams;

  const sendMessageAndStream = useCallback(async (text: string, activeId: string) => {
    const B = window.location.origin;
    const H: Record<string, string> = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${DEFAULT_TOKEN}`,
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
            if (parsed.chunk) {
              updateLastAssistantRef.current(parsed.chunk, 'sse-');
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const newChat = () => {
    setSearchParams({});
    clearMessages();
  };

  const suggestions = [
    '帮我规划一次旅行',
    '推荐几本好书',
    '总结今天的新闻要点',
    '帮我写一封邮件',
  ];

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
        {/* ── Thinking bar (above all content) ──────────────── */}
        {(streamingUi || thinkingExpanded) && (
          <div className="px-4 md:px-6 pt-3">
            <div className="max-w-3xl mx-auto">
              <button
                onClick={() => setThinkingExpanded(!thinkingExpanded)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all w-full group"
                style={{
                  background: 'rgba(184,192,255,0.06)',
                  border: '1px solid rgba(184,192,255,0.12)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {thinkingExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                )}
                <Brain className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-holo)' }} />
                <span className="flex-1 text-left">
                  {streamingUi ? '思考中…' : '思考过程'}
                </span>
                {streamingUi && (
                  <span className="flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full animate-loading-dot-1" style={{ background: 'var(--color-holo)' }} />
                    <span className="w-1 h-1 rounded-full animate-loading-dot-2" style={{ background: 'var(--color-holo)' }} />
                    <span className="w-1 h-1 rounded-full animate-loading-dot-3" style={{ background: 'var(--color-holo)' }} />
                  </span>
                )}
              </button>
              {thinkingExpanded && (
                <div
                  className="mt-1.5 px-3 py-2 rounded-lg text-[12px] leading-relaxed max-h-32 overflow-y-auto"
                  style={{
                    background: 'rgba(184,192,255,0.03)',
                    border: '1px solid rgba(184,192,255,0.08)',
                    color: 'var(--color-text-muted)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {chat.messages.filter(m => m.id.startsWith('sse-') || m.id.startsWith('streaming-')).map(m => m.content).join('') || '正在分析…'}
                </div>
              )}
            </div>
          </div>
        )}
        {!activeId && chat.messages.length === 0 ? (
          <section className="flex flex-col items-center flex-1 justify-center px-4 pb-16">
            <div
              className="w-18 h-18 rounded-2xl flex items-center justify-center mb-6"
              style={{
                background: 'linear-gradient(135deg, rgba(255,107,107,0.15), rgba(0,240,255,0.1))',
                border: '1px solid rgba(255,107,107,0.15)',
              }}
            >
              <Sparkles className="w-8 h-8" style={{ color: 'var(--color-accent)' }} />
            </div>
            <h2 className="text-2xl font-bold tracking-tight mb-2" style={{ color: 'var(--color-text-primary)' }}>有什么可以帮你？</h2>
            <p className="text-[13px] mb-8" style={{ color: 'var(--color-text-secondary)' }}>
              把问题丢给 EvoGen
            </p>

            <div className="grid grid-cols-2 gap-2 w-full max-w-md">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  className="flex items-center gap-2 px-3 py-2.5 rounded-[14px] text-[13px] text-left transition-all duration-200"
                  style={{
                    background: 'var(--color-bg-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-secondary)',
                  }}
                  onClick={() => { setInput(s); }}
                >
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                  <span className="truncate">{s}</span>
                </button>
              ))}
            </div>
          </section>
        ) : (
          <section className="flex flex-col flex-1 pt-2 md:pt-4 px-4 md:px-6 pb-4 max-w-3xl mx-auto w-full">
            <div className="flex-1 space-y-6">
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
                  <div
                    key={msg.id}
                    className={cn('flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : '')}
                  >
                    <div
                      className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={
                        msg.role === 'user'
                          ? { background: 'linear-gradient(135deg, var(--color-accent), var(--color-coral))' }
                          : { background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)' }
                      }
                    >
                      {msg.role === 'user' ? (
                        <User style={{ width: 14, height: 14, color: '#fff' }} />
                      ) : (
                        <Bot className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
                      )}
                    </div>
                    <div className={cn('max-w-[75%]', msg.role === 'user' ? 'items-end' : '')}>
                      {/* Loading dots for streaming messages */}
                      {isStreaming && !msg.content && (
                        <div className="flex items-center gap-1.5 px-4 py-3">
                          <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-1" style={{ background: 'var(--color-accent)' }} />
                          <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-2" style={{ background: 'var(--color-coral)' }} />
                          <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-3" style={{ background: 'var(--color-holo)' }} />
                        </div>
                      )}
                      {msg.content && (
                        <div
                          className={cn(
                            'rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed',
                            msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md',
                          )}
                          style={
                            msg.role === 'user'
                              ? {
                                  background: 'linear-gradient(135deg, var(--color-accent), var(--color-coral))',
                                  color: '#fff',
                                }
                              : {
                                  background: 'var(--color-bg-surface)',
                                  border: '1px solid var(--color-border)',
                                  color: 'var(--color-text-primary)',
                                }
                          }
                        >
                          <div className="whitespace-pre-wrap break-words">
                            {msg.content}
                          </div>
                        </div>
                      )}
                      {/* Show loading dots alongside content that's still streaming */}
                      {isStreaming && msg.content && (
                        <div className="flex items-center gap-1 mt-1.5 px-1">
                          <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-1" style={{ background: 'var(--color-accent)' }} />
                          <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-2" style={{ background: 'var(--color-coral)' }} />
                          <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-3" style={{ background: 'var(--color-holo)' }} />
                        </div>
                      )}
                      <p className="text-[10px] mt-1 px-1" style={{ color: 'var(--color-text-muted)' }}>
                        {formatTime(msg.timestamp)}
                      </p>
                    </div>
                  </div>
                )})
              )}
              <div ref={messagesEndRef} />
            </div>
          </section>
        )}

        {/* Input */}
        <div className="sticky bottom-0 pt-4 pb-4" style={{ background: 'var(--color-bg-deep)' }}>
          <div
            className="flex items-end gap-2 rounded-2xl p-2 max-w-2xl mx-auto transition-all"
            style={{
              background: 'var(--color-bg-surface)',
              border: '1px solid var(--color-border)',
            }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息…"
              rows={1}
              className="flex-1 bg-transparent border-none resize-none focus:outline-none text-[13px] py-1.5 px-2"
              style={{ color: 'var(--color-text-primary)', boxShadow: 'none' }}
            />
            <button
              className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 disabled:opacity-30 transition-all hover:scale-105"
              style={{ background: 'linear-gradient(135deg, var(--color-accent), var(--color-coral))' }}
              onClick={handleSend}
              disabled={!input.trim() || streamingUi}
            >
              <Send style={{ width: 14, height: 14, color: '#fff' }} />
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
