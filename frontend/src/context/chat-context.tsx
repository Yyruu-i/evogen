import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { ChatMsg, ToolCallInfo } from '@/types';
import { generateId } from '@/lib/utils';

interface ChatState {
  messages: ChatMsg[];
  streaming: boolean;
  activeSessionId: string;
  toolCalls: ToolCallInfo[]; // 当前 streaming 消息的 tool calls（按 callId 聚合）
}

interface ChatContextType {
  state: ChatState;
  setMessages: (msgs: ChatMsg[] | ((prev: ChatMsg[]) => ChatMsg[])) => void;
  setStreaming: (v: boolean) => void;
  setActiveSession: (id: string) => void;
  updateLastAssistant: (chunk: string, prefix: string) => void;
  finalizeLastAssistant: () => void;
  clearMessages: () => void;
  setReasoning: (content: string) => void;
  /** 添加或更新一个 tool call（按 callId 聚合） */
  updateToolCall: (info: Partial<ToolCallInfo> & { callId: string }) => void;
  /** 清空当前 tool calls 列表 */
  clearToolCalls: () => void;
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ChatState>({ messages: [], streaming: false, activeSessionId: '', toolCalls: [] });

  const setMessages = useCallback((msgs: ChatMsg[] | ((prev: ChatMsg[]) => ChatMsg[])) => {
    setState((prev) => ({ ...prev, messages: typeof msgs === 'function' ? msgs(prev.messages) : msgs }));
  }, []);

  const setStreaming = useCallback((v: boolean) => {
    setState((prev) => ({ ...prev, streaming: v }));
  }, []);

  const setActiveSession = useCallback((id: string) => {
    setState((prev) => ({ ...prev, activeSessionId: id }));
  }, []);

  const updateLastAssistant = useCallback((chunk: string, prefix: string) => {
    setState((prev) => {
      const msgs = prev.messages;
      const last = msgs[msgs.length - 1];
      // Pre-compute reasoning from thinking- msg before replacement
      let accumulatedReasoning: string | undefined = undefined;
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].id.startsWith('thinking-') && msgs[i].reasoning) {
          accumulatedReasoning = msgs[i].reasoning;
          break;
        }
      }
      // 如果最后一条是 thinking 占位，替换掉它（保留已累积的 reasoning）
      if (last?.role === 'assistant' && last.id.startsWith('thinking-')) {
        const newMsg = {
          id: `${prefix}${Date.now()}`,
          role: 'assistant' as const,
          content: chunk,
          timestamp: new Date().toISOString(),
          reasoning: accumulatedReasoning,
          toolCalls: prev.toolCalls.length > 0 ? [...prev.toolCalls] : undefined,
        };
        return { ...prev, messages: [...msgs.slice(0, -1), newMsg] };
      }
      if (last?.role === 'assistant' && last.id.startsWith(prefix)) {
        // 只有 chunk 有内容才更新 content；否则只更新 toolCalls（避免闪烁）
        const updated = { ...last, toolCalls: prev.toolCalls.length > 0 ? [...prev.toolCalls] : last.toolCalls };
        if (chunk) updated.content = last.content + chunk;
        return { ...prev, messages: [...msgs.slice(0, -1), updated] };
      }
      // 没有最后一条消息或不是流式 ID，创建新消息
      const newMsg = {
        id: `${prefix}${Date.now()}`,
        role: 'assistant' as const,
        content: chunk || '',
        timestamp: new Date().toISOString(),
        toolCalls: prev.toolCalls.length > 0 ? [...prev.toolCalls] : undefined,
      };
      return { ...prev, messages: [...msgs, newMsg] };
    });
  }, []);

  const finalizeLastAssistant = useCallback(() => {
    setState((prev) => {
      const last = prev.messages[prev.messages.length - 1];
      if (last?.id.startsWith('sse-') || last?.id.startsWith('streaming-')) {
        return { ...prev, messages: [...prev.messages.slice(0, -1), { ...last, id: generateId(), toolCalls: prev.toolCalls.length > 0 ? [...prev.toolCalls] : undefined }] };
      }
      return prev;
    });
  }, []);

  const clearMessages = useCallback(() => {
    setState({ messages: [], streaming: false, activeSessionId: '', toolCalls: [] });
  }, []);

  const setReasoning = useCallback((content: string) => {
    setState((prev) => {
      const msgs = prev.messages;
      const idx = msgs.length - 1;
      if (idx < 0 || msgs[idx].role !== 'assistant') return prev;
      const updated = [...msgs];
      updated[idx] = { ...updated[idx], reasoning: (updated[idx].reasoning || '') + content };
      return { ...prev, messages: updated };
    });
  }, []);

  const updateToolCall = useCallback((info: Partial<ToolCallInfo> & { callId: string }) => {
    setState((prev) => {
      const existing = prev.toolCalls.find((tc) => tc.callId === info.callId);
      if (existing) {
        // 更新已有的
        return {
          ...prev,
          toolCalls: prev.toolCalls.map((tc) =>
            tc.callId === info.callId ? { ...tc, ...info } : tc
          ),
        };
      }
      // 新增
      return {
        ...prev,
        toolCalls: [...prev.toolCalls, info as ToolCallInfo],
      };
    });
  }, []);

  const clearToolCalls = useCallback(() => {
    setState((prev) => ({ ...prev, toolCalls: [] }));
  }, []);

  return (
    <ChatContext.Provider value={{ state, setMessages, setStreaming, setActiveSession, updateLastAssistant, finalizeLastAssistant, clearMessages, setReasoning, updateToolCall, clearToolCalls }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}
