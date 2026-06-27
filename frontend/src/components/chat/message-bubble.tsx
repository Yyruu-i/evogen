import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { User, Bot, Wrench, ChevronDown, ChevronRight, Brain } from 'lucide-react';
import { formatTime, cn } from '@/lib/utils';

interface MessageBubbleProps {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp?: string;
  isStreaming?: boolean;
  reasoning?: string; // R1 模型的原生 reasoning_content
}

export function MessageBubble({ role, content, timestamp, isStreaming, reasoning }: MessageBubbleProps) {
  const isUser = role === 'user';
  const isTool = role === 'tool';
  const [thinkingOpen, setThinkingOpen] = useState(true);

  // 仅 assistant 有 reasoning 时展示思考折叠条（R1 模型）
  const hasReasoning = !isUser && !isTool && reasoning;

  return (
    <div className={cn('flex gap-3 group', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div
        className={cn(
          'w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0',
        )}
        style={
          isUser
            ? { background: 'var(--chat-bubble-user)' }
            : isTool
              ? { background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)' }
              : { background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)' }
        }
      >
        {isUser ? (
          <User style={{ width: 14, height: 14, color: '#fff' }} />
        ) : isTool ? (
          <Wrench className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
        ) : (
          <Bot className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
        )}
      </div>

      {/* Bubble */}
      <div className={cn('max-w-[75%]', isUser && 'items-end')}>
        {/* Loading dots for empty streaming messages */}
        {isStreaming && !content && (
          <div className="flex items-center gap-1.5 px-4 py-3">
            <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-1" style={{ background: 'var(--color-accent)' }} />
            <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-2" style={{ background: 'var(--color-coral)' }} />
            <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-3" style={{ background: 'var(--color-holo)' }} />
          </div>
        )}

        {content && (
          <div className="flex flex-col gap-1">
            {/* ── R1 思考过程：豆包风格内嵌折叠 ── */}
            {hasReasoning && (
              <div
                className="rounded-2xl overflow-hidden"
                style={{
                  background: 'var(--chat-bubble-assistant)',
                  border: '1px solid var(--chat-bubble-assistant-border)',
                  boxShadow: 'var(--chat-bubble-shadow)',
                }}
              >
                <button
                  onClick={() => setThinkingOpen(!thinkingOpen)}
                  className="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium transition-all w-full select-none hover:opacity-80"
                  style={{
                    background: 'transparent',
                    color: 'var(--color-text-secondary)',
                  }}
                >
                  <Brain className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
                  <span className="flex-1 text-left">已深度思考</span>
                  {thinkingOpen ? (
                    <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                  )}
                </button>
                {thinkingOpen && (
                  <div
                    className="px-4 py-2.5 text-[12px] leading-relaxed max-h-64 overflow-y-auto"
                    style={{
                      color: 'var(--color-text-muted)',
                      fontFamily: 'var(--font-mono)',
                      whiteSpace: 'pre-wrap',
                      borderTop: '1px solid var(--color-border-glass)',
                    }}
                  >
                    {reasoning}
                  </div>
                )}
              </div>
            )}

            {/* ── Answer content (normal markdown) ── */}
            <div
              className={cn(
                'px-4 py-2.5 text-[14px] leading-relaxed',
                (isUser
                  ? 'rounded-2xl rounded-br-md text-white'
                  : 'rounded-2xl rounded-bl-md'),
              )}
              style={
                isUser
                  ? {
                      background: 'var(--chat-bubble-user)',
                      color: 'var(--chat-bubble-user-text)',
                      boxShadow: 'var(--chat-bubble-shadow)',
                    }
                  : {
                      background: 'var(--chat-bubble-assistant)',
                      border: '1px solid var(--chat-bubble-assistant-border)',
                      color: 'var(--chat-bubble-assistant-text)',
                      boxShadow: 'var(--chat-bubble-shadow)',
                    }
              }
            >
              {/* Content rendering: user/tool plain text; assistant with markdown */}
              {isUser || isTool ? (
                <div className="whitespace-pre-wrap break-words">
                  {content}
                </div>
              ) : (
                <div className="prose prose-sm max-w-none [&_pre]:!my-2 [&_pre]:!rounded-lg [&_code]:!text-xs [&_p]:!my-1 [&_ul]:!my-1 [&_ol]:!my-1 [&_table]:!text-xs">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {content}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Streaming indicator alongside content */}
        {isStreaming && content && (
          <div className="flex items-center gap-1 mt-1.5 px-1">
            <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-1" style={{ background: 'var(--color-accent)' }} />
            <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-2" style={{ background: 'var(--color-coral)' }} />
            <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-3" style={{ background: 'var(--color-holo)' }} />
          </div>
        )}

        {/* Timestamp */}
        {timestamp && !isStreaming && (
          <p className="text-[10px] mt-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--color-text-muted)' }}>
            {formatTime(timestamp)}
          </p>
        )}
      </div>
    </div>
  );
}
