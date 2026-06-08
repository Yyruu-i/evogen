import { useRef, useEffect } from 'react';
import { Send, Square } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop?: () => void;
  disabled?: boolean;
  streaming?: boolean;
  placeholder?: string;
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  disabled,
  streaming,
  placeholder = '输入消息…',
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && !streaming && value.trim()) {
        onSend();
      }
    }
  };

  return (
    <div className="sticky bottom-0 pt-3 pb-4 z-10" style={{ background: 'var(--color-bg-deep)' }}>
      <div className="max-w-3xl mx-auto px-4 md:px-6">
        <div
          className={cn(
            'flex items-end gap-2 p-2 transition-all duration-200',
            'rounded-2xl',
          )}
          style={{
            background: 'var(--chat-input-bg)',
            border: '1px solid var(--chat-input-border)',
            borderRadius: 'var(--chat-input-radius)',
            boxShadow: 'var(--chat-input-shadow)',
          }}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            disabled={disabled}
            className="flex-1 bg-transparent border-none resize-none focus:outline-none text-[13px] py-1.5 px-2"
            style={{
              color: 'var(--color-text-primary)',
              boxShadow: 'none',
              maxHeight: '160px',
            }}
          />

          {/* Send / Stop button */}
          {streaming ? (
            <button
              onClick={onStop}
              className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all hover:scale-105"
              style={{ background: 'var(--color-danger)' }}
              title="停止生成"
            >
              <Square style={{ width: 14, height: 14, color: '#fff' }} />
            </button>
          ) : (
            <button
              onClick={onSend}
              disabled={disabled || !value.trim()}
              className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all hover:scale-105 disabled:opacity-30 disabled:cursor-not-allowed"
              style={{ background: 'linear-gradient(135deg, var(--color-accent), var(--color-coral))' }}
            >
              <Send style={{ width: 14, height: 14, color: '#fff' }} />
            </button>
          )}
        </div>

        {/* Shortcut hint */}
        <p
          className="text-[10px] text-center mt-1.5 select-none"
          style={{ color: 'var(--color-text-muted)' }}
        >
          Enter 发送 · Shift + Enter 换行
        </p>
      </div>
    </div>
  );
}
