import type { ToolCallInfo } from '@/types';
import { ToolCallCard } from './tool-call-card';
import { useState, useMemo } from 'react';
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
  toolCalls?: ToolCallInfo[]; // 工具调用卡片
}

/**
 * 从 assistant 的完整 content 中提取思考过程和回答正文。
 * - 有 【思考过程】标签 → 提取为 thinking，剩余作为 answer
 * - 无标签 → 返回 { thinking: null, answer: text }（chat 模型走这个分支）
 */
function parseThinkingContent(text: string): { thinking: string | null; answer: string } {
  const thinkingMatch = text.match(/【思考过程】\s*([\s\S]*?)\s*【\/思考过程】/);
  const thinking = thinkingMatch ? thinkingMatch[1].trim() : null;

  let answer = text;
  if (thinking) {
    answer = text.replace(/【思考过程】[\s\S]*?【\/思考过程】/, '').trim();
  }

  return { thinking, answer };
}

export function MessageBubble({ role, content, timestamp, isStreaming, reasoning, toolCalls }: MessageBubbleProps) {
  const isUser = role === 'user';
  const isTool = role === 'tool';
  const isAssistant = !isUser && !isTool;
  const [thinkingOpen, setThinkingOpen] = useState(true);

  // 前端解析正文中的思考过程标签（v4 模型）
  const parsed = useMemo(() => {
    if (!isAssistant) return { thinking: null, answer: content };
    return parseThinkingContent(content);
  }, [content, isAssistant]);

  // 展示思考折叠的条件：
  // 1. r1 原生 reasoning（从 SSE 的 reasoning 事件来）
  // 2. v4 前端从 content 解析出思考标签
  const hasR1Reasoning = isAssistant && !!reasoning;
  const hasV4Thinking = isAssistant && !!parsed.thinking;
  const showThinkingBlock = hasR1Reasoning || hasV4Thinking;

  // 思考折叠块显示的内容
  const thinkingContent = reasoning || parsed.thinking || '';

  // 显示的正文：user/tool 用原 content，assistant 用剥离后的 answer
  const displayContent = isAssistant ? parsed.answer : content;

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
            {/* ── 思考折叠块（r1 原生 reasoning / v4 标签提取） ── */}
            {showThinkingBlock && (
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
                    {thinkingContent}
                  </div>
                )}
              </div>
            )}

            {/* ── Tool call cards ── */}
            {isAssistant && toolCalls && toolCalls.length > 0 && (
              <div className="flex flex-col gap-2">
                {toolCalls.map((tc) => (
                  <ToolCallCard key={tc.callId} call={tc} />
                ))}
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
                  {displayContent}
                </div>
              ) : (
                <div className="prose prose-sm max-w-none [&_pre]:!my-2 [&_pre]:!rounded-lg [&_code]:!text-xs [&_p]:!my-1 [&_ul]:!my-1 [&_ol]:!my-1 [&_table]:!text-xs">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {displayContent}
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
