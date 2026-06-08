import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { User, Bot, Wrench } from 'lucide-react';
import { formatTime, cn } from '@/lib/utils';

interface MessageBubbleProps {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp?: string;
  isStreaming?: boolean;
}

export function MessageBubble({ role, content, timestamp, isStreaming }: MessageBubbleProps) {
  const isUser = role === 'user';
  const isTool = role === 'tool';

  return (
    <div className={cn('flex gap-3 group', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div
        className={cn(
          'w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0',
          isUser
            ? ''
            : isTool
              ? ''
              : '',
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
          <div
            className={cn(
              'px-4 py-2.5 text-[13px] leading-relaxed',
              isUser
                ? 'rounded-2xl rounded-br-md text-white'
                : 'rounded-2xl rounded-bl-md',
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
                    border: `1px solid var(--chat-bubble-assistant-border)`,
                    color: 'var(--chat-bubble-assistant-text)',
                    boxShadow: 'var(--chat-bubble-shadow)',
                  }
            }
          >
            {/* Markdown rendering for assistant/tool messages, plain text for user */}
            {isUser ? (
              <div className="whitespace-pre-wrap break-words">{content}</div>
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
