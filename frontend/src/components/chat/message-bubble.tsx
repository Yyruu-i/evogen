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
}

interface ParsedThinking {
  thinking: string;
  answer: string;
}

/**
 * Strip JSON tool-call data from content before parsing thinking/answer tags.
 * Matches: {"status":"tool_...", ...} or {"status":"browser_...", ...}
 * These are produced by the LLM and injected between tags; they should
 * never be visible to the user.
 */
function stripToolJson(content: string): string {
  // Remove top-level JSON objects that start with {"status":
  // Uses a non-greedy match across lines to the first closing brace.
  // Tool JSON from the LLM is always flat (no nested braces), so
  // matching to the first } is safe.
  return content.replace(/\{\s*"status"\s*:\s*"[^"]*".*?\}/gs, '');
}

/**
 * Parse content for 【思考过程】 / 【/思考过程】 and 【回答】 / 【/回答】 tags.
 * First strips tool JSON data, then parses tags.
 * Uses full closing tags so the model can explicitly mark boundaries.
 * Returns { thinking, answer } or null if no tags found.
 */
function parseThinkingContent(content: string): ParsedThinking | null {
  // Strip tool JSON before parsing tags
  const cleaned = stripToolJson(content);

  const thinkRegex = /【思考过程】\s*([\s\S]*?)【\/思考过程】/;
  const answerRegex = /【回答】\s*([\s\S]*?)【\/回答】/;

  const thinkMatch = cleaned.match(thinkRegex);
  const answerMatch = cleaned.match(answerRegex);

  if (thinkMatch || answerMatch) {
    return {
      thinking: thinkMatch ? thinkMatch[1].trim() : '',
      answer: answerMatch ? answerMatch[1].trim() : cleaned
        // If only answer tags but no thinking tags, strip answer tags from the answer text
        .replace(/【回答】\s*/, '')
        .replace(/\s*【\/回答】/, ''),
    };
  }

  return null;
}

export function MessageBubble({ role, content, timestamp, isStreaming }: MessageBubbleProps) {
  const isUser = role === 'user';
  const isTool = role === 'tool';
  const [thinkingOpen, setThinkingOpen] = useState(true);

  // Only parse thinking/answer for assistant messages
  const parsed = !isUser && !isTool ? parseThinkingContent(content) : null;

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
          <div className="flex flex-col gap-2">
            {/* ── Thinking section (collapsible card) ── */}
            {parsed && parsed.thinking && (
              <div
                className="rounded-2xl rounded-bl-md overflow-hidden"
                style={{
                  background: 'var(--chat-bubble-assistant)',
                  border: '1px solid var(--chat-bubble-assistant-border)',
                  boxShadow: 'var(--chat-bubble-shadow)',
                }}
              >
                <button
                  onClick={() => setThinkingOpen(!thinkingOpen)}
                  className="flex items-center gap-2 px-4 py-2 text-[12px] font-medium transition-all w-full"
                  style={{
                    background: 'rgba(184,192,255,0.06)',
                    borderBottom: thinkingOpen ? '1px solid var(--color-border-glass)' : 'none',
                    color: 'var(--color-text-secondary)',
                  }}
                >
                  {thinkingOpen ? (
                    <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                  )}
                  <Brain className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-holo)' }} />
                  <span className="flex-1 text-left">思考过程</span>
                </button>
                {thinkingOpen && (
                  <div
                    className="px-4 py-2.5 text-[12px] leading-relaxed max-h-64 overflow-y-auto"
                    style={{
                      color: 'var(--color-text-muted)',
                      fontFamily: 'var(--font-mono)',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {parsed.thinking}
                  </div>
                )}
              </div>
            )}

            {/* ── Answer content (normal markdown) ── */}
            <div
              className={cn(
                'px-4 py-2.5 text-[13px] leading-relaxed',
                !parsed && (isUser
                  ? 'rounded-2xl rounded-br-md text-white'
                  : 'rounded-2xl rounded-bl-md'),
                parsed && 'rounded-2xl rounded-bl-md',
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
                  {parsed ? parsed.answer : content}
                </div>
              ) : (
                <div className="prose prose-sm max-w-none [&_pre]:!my-2 [&_pre]:!rounded-lg [&_code]:!text-xs [&_p]:!my-1 [&_ul]:!my-1 [&_ol]:!my-1 [&_table]:!text-xs">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {parsed ? parsed.answer : content}
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
