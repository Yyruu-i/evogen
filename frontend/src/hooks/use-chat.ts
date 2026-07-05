import { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useSessionMessages } from '@/hooks/use-sessions';
import { EvoGenWS } from '@/lib/ws';
import { cn, generateId } from '@/lib/utils';
import { useQueryClient } from '@tanstack/react-query';
import { useChatContext } from '@/context/chat-context';
import { useWsStatus } from '@/context/ws-context';
import type { ChatMsg, WsAgentEvent } from '@/types';

interface UseChatOptions {
  mode: 'normal' | 'expert';
  expertId?: string;
}

interface UseChatReturn {
  activeId: string;
  input: string;
  setInput: (v: string) => void;
  streamingUi: boolean;
  msgsLoading: boolean;
  chatMessages: ChatMsg[];
  wsStatus: ReturnType<typeof useWsStatus>['wsStatus'];
  handleSend: () => void;
  handleSendFile: (content: string) => void;
  handleStop: () => void;
  newChat: () => void;
  messagesEndRef: React.RefObject<HTMLDivElement>;
}

export function useChat({ mode, expertId }: UseChatOptions): UseChatReturn {
  const [searchParams, setSearchParams] = useSearchParams();
  // 专家模式：忽略 URL session
  const urlSession = mode === 'normal' ? searchParams.get('session') || '' : '';
  const [activeId, setActiveIdPrivate] = useState(urlSession);
  // 同步 URL session 到 state（仅 normal 模式）
  useEffect(() => {
    if (mode === 'normal') {
      setActiveIdPrivate(searchParams.get('session') || '');
    }
  }, [searchParams, mode]);

  const [input, setInput] = useState('');
  const { wsStatus, setWsStatus } = useWsStatus();
  const wsRef = useRef<EvoGenWS | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null!);
  const pendingSessionRef = useRef<string | null>(null);
  // 专家独立 session ref（不依赖 URL 也不依赖 ChatContext）
  const expertSessionRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const [streamingUi, setStreamingUi] = useState(false);
  const qc = useQueryClient();

  // 专家模式：完全自有的 messages state
  const [localMessages, setLocalMessages] = useState<ChatMsg[]>([]);
  const { state: chat, setMessages, setStreaming, setActiveSession, updateLastAssistant, finalizeLastAssistant, clearMessages, setReasoning, updateToolCall, clearToolCalls } = useChatContext();

  // 选择 messages 来源
  const chatMessages = mode === 'expert' ? localMessages : chat.messages;

  const { data: msgData, isLoading: msgsLoading } = useSessionMessages(
    mode === 'normal' ? activeId : ''
  );

  // Sync active session ID to context (only normal mode)
  useEffect(() => {
    if (mode === 'normal' && activeId) setActiveSession(activeId);
  }, [activeId, setActiveSession, mode]);

  // Load messages from backend when session changes (normal mode only)
  useEffect(() => {
    if (mode === 'normal') {
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
    }
  }, [msgData, activeId, msgsLoading, setMessages, mode]);

  // 专家模式：进入时清空 local messages（全新对话）
  useEffect(() => {
    if (mode === 'expert') {
      setLocalMessages([]);
      expertSessionRef.current = null;
    }
  // 只在 mount/unmount 时执行
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setChatMessages = useCallback((msgs: ChatMsg[] | ((prev: ChatMsg[]) => ChatMsg[])) => {
    if (mode === 'expert') {
      setLocalMessages(prev => typeof msgs === 'function' ? msgs(prev) : msgs);
    } else {
      setMessages(msgs);
    }
  }, [mode, setMessages]);

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
        if (mode === 'normal' && activeId) {
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
  }, [chatMessages]);

  // Stable refs for async callbacks
  const updateLastAssistantRef = useRef(updateLastAssistant);
  updateLastAssistantRef.current = updateLastAssistant;
  const finalizeLastAssistantRef = useRef(finalizeLastAssistant);
  finalizeLastAssistantRef.current = finalizeLastAssistant;
  const setReasoningRef = useRef(setReasoning);
  setReasoningRef.current = setReasoning;
  const setSearchParamsRef = useRef(setSearchParams);
  setSearchParamsRef.current = setSearchParams;
  const setMessagesRef = useRef(setChatMessages);
  setMessagesRef.current = setChatMessages;
  const updateToolCallRef = useRef(updateToolCall);
  updateToolCallRef.current = updateToolCall;
  const clearToolCallsRef = useRef(clearToolCalls);
  clearToolCallsRef.current = clearToolCalls;

  const sendMessageAndStream = useCallback(async (text: string, sessionId: string) => {
    const B = window.location.origin;
    const token = (() => { try { return localStorage.getItem('evogen-auth-token') || ''; } catch { return ''; } })();
    const H: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    };
    const body: Record<string, unknown> = { message: text };
    if (sessionId) body.session = sessionId;
    if (expertId) body.expert_id = expertId;

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
            if (parsed.session && !sessionId) {
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
            // ── 处理智能编排步骤进度 ──
            if (parsed.status === 'orchestrator_step' && parsed.message) {
              updateLastAssistantRef.current(
                '\n> 🛡️ ' + parsed.message,
                'sse-'
              );
            }
            // ── 处理 tool_start —— 创建 tool call 条目 ──
            if (parsed.status === 'tool_start' && parsed.callId) {
              updateToolCallRef.current({
                callId: parsed.callId,
                toolName: parsed.tool,
                args: JSON.stringify(parsed.args || {}),
                timestamp: parsed.timestamp,
              });
            }
            // ── 处理 tool_result —— 补全 tool call 结果 ──
            if (parsed.status === 'tool_result' && parsed.callId) {
              updateToolCallRef.current({
                callId: parsed.callId,
                result: parsed.result || '',
                costTime: parsed.costTime,
                errorMsg: parsed.errorMsg || '',
                success: !parsed.errorMsg,
                timestamp: parsed.timestamp,
              });
            }
            // ── 处理 tool_failure —— 标记失败 ──
            if (parsed.status === 'tool_failure' && parsed.callId) {
              updateToolCallRef.current({
                callId: parsed.callId,
                success: false,
              });
            }
            // ── 处理进度 —— 更新工具执行进度 ──
            if (parsed.status === 'progress' && parsed.callId) {
              updateToolCallRef.current({
                callId: parsed.callId,
                progress: `${parsed.current || 0}/${parsed.total || 0}`,
                progressDetail: parsed.detail || '',
              });
            }
          } catch {
            // 非 JSON 数据忽略
          }
        }
      }
    } catch (err) {
      console.warn('SSE stream error:', err);
    }

    finalizeLastAssistantRef.current();
    // 清理可能的 thinking 占位
    setMessagesRef.current(prev => prev.filter(m => !m.id.startsWith('thinking-')));
    if (pendingSessionRef.current) {
      if (mode === 'expert') {
        // 专家模式：存到 expertSessionRef，不写 URL
        expertSessionRef.current = pendingSessionRef.current;
      } else {
        setSearchParamsRef.current({ session: pendingSessionRef.current });
      }
      pendingSessionRef.current = null;
    }
  }, [expertId, mode]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || streamingRef.current) return;
    const userMsg: ChatMsg = { id: generateId(), role: 'user', content: text, timestamp: new Date().toISOString() };
    const thinkingMsg: ChatMsg = { id: 'thinking-' + Date.now(), role: 'assistant', content: '', timestamp: new Date().toISOString() };
    // 用正确的 messages 源
    const currentMsgs = mode === 'expert' ? localMessages : chat.messages;
    setChatMessages([...currentMsgs, userMsg, thinkingMsg]);
    setInput('');
    streamingRef.current = true;
    setStreamingUi(true);

    // 专家模式用 expertSessionRef，normal 模式用 URL session
    const effectiveSession = mode === 'expert'
      ? (expertSessionRef.current || '')
      : (activeId || chat.activeSessionId);
    clearToolCallsRef.current();
    sendMessageAndStream(text, effectiveSession).finally(() => {
      streamingRef.current = false;
      setTimeout(() => {
        setStreamingUi(false);
      }, 800);
      qc.invalidateQueries({ queryKey: ['sessions'] });
      if (mode === 'normal' && activeId) {
        qc.invalidateQueries({ queryKey: ['sessions', activeId, 'messages'] });
      }
    });
  // activeId 也要进 deps，但 expert 模式用 expertSessionRef
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, activeId, chat.messages, localMessages, setChatMessages, qc, mode]);

  const handleSendFile = useCallback((content: string) => {
    const text = content.trim();
    if (!text || streamingRef.current) return;
    const userMsg: ChatMsg = { id: generateId(), role: 'user', content: text, timestamp: new Date().toISOString() };
    const thinkingMsg: ChatMsg = { id: 'thinking-' + Date.now(), role: 'assistant', content: '', timestamp: new Date().toISOString() };
    const currentMsgs = mode === 'expert' ? localMessages : chat.messages;
    setChatMessages([...currentMsgs, userMsg, thinkingMsg]);
    streamingRef.current = true;
    setStreamingUi(true);

    const effectiveSession = mode === 'expert'
      ? (expertSessionRef.current || '')
      : (activeId || chat.activeSessionId);
    sendMessageAndStream(text, effectiveSession).finally(() => {
      streamingRef.current = false;
      setTimeout(() => {
        setStreamingUi(false);
      }, 800);
      qc.invalidateQueries({ queryKey: ['sessions'] });
      if (mode === 'normal' && activeId) {
        qc.invalidateQueries({ queryKey: ['sessions', activeId, 'messages'] });
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, chat.messages, localMessages, setChatMessages, qc, mode]);

  // Stop streaming
  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    streamingRef.current = false;
    setStreamingUi(false);
    setStreaming(false);
    setChatMessages(prev => prev.filter(m => !m.id.startsWith('thinking-')));
    finalizeLastAssistant();
  }, [finalizeLastAssistant, setStreaming, setChatMessages]);

  const newChat = () => {
    if (mode === 'expert') {
      setLocalMessages([]);
      expertSessionRef.current = null;
    } else {
      setSearchParams({});
      clearMessages();
    }
  };

  return {
    activeId,
    input,
    setInput,
    streamingUi,
    msgsLoading,
    chatMessages,
    wsStatus,
    handleSend,
    handleSendFile,
    handleStop,
    newChat,
    messagesEndRef,
  };
}
