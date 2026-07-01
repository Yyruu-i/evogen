import { Bot, Brain } from 'lucide-react';

/**
 * 思考中气泡 — 消息发出后立即显示，表示 AI 正在处理。
 * 第一个 SSE chunk 到达后会被正常 assistant 消息覆盖。
 */
export function ThinkingBubble() {
  return (
    <div className="flex gap-3 group">
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{
          background: 'var(--color-bg-tertiary)',
          border: '1px solid var(--color-border)',
        }}
      >
        <Bot className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
      </div>

      {/* 思考中折叠块 */}
      <div className="max-w-[75%]">
        <div
          className="rounded-2xl overflow-hidden"
          style={{
            background: 'var(--chat-bubble-assistant)',
            border: '1px solid var(--chat-bubble-assistant-border)',
            boxShadow: 'var(--chat-bubble-shadow)',
          }}
        >
          <div className="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <Brain className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
            <span className="flex-1 text-left">正在思考...</span>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-1" style={{ background: 'var(--color-accent)' }} />
              <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-2" style={{ background: 'var(--color-coral)' }} />
              <span className="w-1.5 h-1.5 rounded-full animate-loading-dot-3" style={{ background: 'var(--color-holo)' }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
