import { useRef, useEffect, useState, useCallback } from 'react';
import { Send, Square, Mic, MicOff } from 'lucide-react';
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
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

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

  const handleVoiceInput = useCallback(() => {
    // Check browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('您的浏览器不支持语音识别，请使用 Chrome 浏览器。');
      return;
    }

    if (isListening) {
      // Stop listening
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0][0].transcript;
      onChange(transcript);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.warn('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'not-allowed') {
        alert('请允许使用麦克风权限。');
      }
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();
    setIsListening(true);
  }, [isListening, onChange]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
    };
  }, []);

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
          {/* Voice input button */}
          <button
            onClick={handleVoiceInput}
            className={cn(
              'w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all hover:scale-105',
              isListening && 'animate-pulse',
            )}
            style={{
              background: isListening
                ? 'rgba(255,68,68,0.15)'
                : 'rgba(184,192,255,0.06)',
              color: isListening ? 'var(--color-danger)' : 'var(--color-text-muted)',
            }}
            title={isListening ? '停止录音' : '语音输入'}
          >
            {isListening ? (
              <MicOff style={{ width: 16, height: 16 }} />
            ) : (
              <Mic style={{ width: 16, height: 16 }} />
            )}
          </button>

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isListening ? '正在聆听…' : placeholder}
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
          Enter 发送 · Shift + Enter 换行 · 麦克风按钮语音输入
        </p>
      </div>
    </div>
  );
}
