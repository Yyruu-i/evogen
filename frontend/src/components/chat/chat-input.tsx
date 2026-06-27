import { useRef, useEffect, useState, useCallback } from 'react';
import { Send, Square, Mic, MicOff, Plus, Paperclip, Image, FileText, X } from 'lucide-react';
import { cn } from '@/lib/utils';

// Type declarations for Web Speech API
// Edge (Chromium) / Chrome 原生支持，国内可直用
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionAPI: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

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
  const [showUploadMenu, setShowUploadMenu] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const uploadMenuRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);

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
    const SR: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      alert('您的浏览器不支持语音识别，请使用 Edge 或 Chrome 浏览器。');
      return;
    }

    if (isListening) {
      // Stop listening
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const recognition = new SR();
    recognitionRef.current = recognition;
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      onChange(transcript);
    };

    recognition.onerror = (event: any) => {
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

  // Close upload menu on outside click
  useEffect(() => {
    if (!showUploadMenu) return;
    const handler = (e: MouseEvent) => {
      if (uploadMenuRef.current && !uploadMenuRef.current.contains(e.target as Node)) {
        setShowUploadMenu(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showUploadMenu]);

  const handleFileUpload = async (file: File, type: 'doc' | 'image') => {
    setShowUploadMenu(false);
    setUploading(true);
    try {
      const token = (() => { try { return localStorage.getItem('evogen-auth-token') || ''; } catch { return ''; } })();
      let content: string;
      if (type === 'image') {
        // 图片：转 base64
        const buffer = await file.arrayBuffer();
        const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
        content = `![${file.name}](data:${file.type};base64,${base64})`;
      } else {
        // 文档：读取为文本
        content = await file.text();
        content = `📄 **上传文件**: ${file.name}\n\n\`\`\`\n${content.slice(0, 5000)}\`\`\`\n\n*（文件前 5000 字符已显示，完整内容已存入系统消息）*`;
      }
      // 插入到输入框
      onChange(content);
    } catch (err) {
      console.error('File upload failed:', err);
      alert('文件读取失败');
    } finally {
      setUploading(false);
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
          {/* Left buttons: Voice + Plus */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {/* Voice input button */}
            <button
              onClick={handleVoiceInput}
              className={cn(
                'w-9 h-9 rounded-xl flex items-center justify-center transition-all hover:scale-105',
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

            {/* + Plus button */}
            <div className="relative" ref={uploadMenuRef}>
              <button
                onClick={() => setShowUploadMenu(!showUploadMenu)}
                className="w-9 h-9 rounded-xl flex items-center justify-center transition-all hover:scale-105"
                style={{
                  background: showUploadMenu ? 'rgba(255,107,107,0.1)' : 'rgba(184,192,255,0.06)',
                  color: showUploadMenu ? 'var(--color-accent)' : 'var(--color-text-muted)',
                }}
                title="上传文件"
              >
                <Plus style={{ width: 16, height: 16 }} />
              </button>

              {/* Upload menu popover */}
              {showUploadMenu && (
                <div
                  className="absolute bottom-full left-0 mb-2 rounded-xl overflow-hidden shadow-lg min-w-[140px]"
                  style={{
                    background: 'var(--color-bg-surface)',
                    border: '1px solid var(--color-border-glass)',
                  }}
                >
                  <button
                    className="flex items-center gap-2 w-full px-3 py-2.5 text-[12px] font-medium transition-colors hover:opacity-80"
                    style={{ color: 'var(--color-text-primary)' }}
                    onClick={() => {
                      document.getElementById('chat-image-input')?.click();
                    }}
                  >
                    <Image className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
                    上传图片
                  </button>
                  <button
                    className="flex items-center gap-2 w-full px-3 py-2.5 text-[12px] font-medium transition-colors hover:opacity-80"
                    style={{ color: 'var(--color-text-primary)' }}
                    onClick={() => {
                      document.getElementById('chat-file-input')?.click();
                    }}
                  >
                    <FileText className="w-4 h-4" style={{ color: 'var(--color-holo)' }} />
                    上传文档
                  </button>
                </div>
              )}

              {/* Hidden file inputs */}
              <input
                id="chat-image-input"
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileUpload(file, 'image');
                }}
              />
              <input
                id="chat-file-input"
                type="file"
                accept=".txt,.md,.pdf,.docx,.csv,.json"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileUpload(file, 'doc');
                }}
              />
            </div>
          </div>

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isListening ? '正在聆听…' : placeholder}
            rows={1}
            disabled={disabled}
            className="flex-1 bg-transparent border-none resize-none focus:outline-none text-[14px] py-1.5 px-2"
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
