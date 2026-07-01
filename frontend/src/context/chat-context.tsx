import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { ChatMsg } from '@/types';
import { generateId } from '@/lib/utils';

interface ChatState {
  messages: ChatMsg[];
  streaming: boolean;
  activeSessionId: string;
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
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ChatState>({ messages: [], streaming: false, activeSessionId: '' });

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
      // 如果最后一条是 thinking 占位，替换掉它
      if (last?.role === 'assistant' && last.id.startsWith('thinking-')) {
        return { ...prev, messages: [...msgs.slice(0, -1), { id: `${prefix}${Date.now()}`, role: 'assistant', content: chunk, timestamp: new Date().toISOString() }] };
      }
      if (last?.role === 'assistant' && last.id.startsWith(prefix)) {
        return { ...prev, messages: [...msgs.slice(0, -1), { ...last, content: last.content + chunk }] };
      }
      return { ...prev, messages: [...msgs, { id: `${prefix}${Date.now()}`, role: 'assistant', content: chunk, timestamp: new Date().toISOString() }] };
    });
  }, []);

  const finalizeLastAssistant = useCallback(() => {
    setState((prev) => {
      const last = prev.messages[prev.messages.length - 1];
      if (last?.id.startsWith('sse-') || last?.id.startsWith('streaming-')) {
        return { ...prev, messages: [...prev.messages.slice(0, -1), { ...last, id: generateId() }] };
      }
      return prev;
    });
  }, []);

  const clearMessages = useCallback(() => {
    setState({ messages: [], streaming: false, activeSessionId: '' });
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

  return (
    <ChatContext.Provider value={{ state, setMessages, setStreaming, setActiveSession, updateLastAssistant, finalizeLastAssistant, clearMessages, setReasoning }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}
