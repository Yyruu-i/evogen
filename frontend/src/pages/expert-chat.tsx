import { useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MessageBubble } from '@/components/chat/message-bubble';
import { ChatInput } from '@/components/chat/chat-input';
import { ThinkingBubble } from '@/components/chat/thinking-bubble';
import { useChat } from '@/hooks/use-chat';

const EXPERT_INFO: Record<string, { name: string; icon: string; color: string }> = {
  'security-engineer': { name: '安全工程师', icon: '🛡️', color: '#ff6b6b' },
  'python-engineer':   { name: 'Python 工程师', icon: '🐍', color: '#4ecdc4' },
  'ops-engineer':      { name: '运维工程师', icon: '⚙️', color: '#45b7d1' },
  'data-analyst':      { name: '数据分析师', icon: '📊', color: '#96ceb4' },
  'doc-engineer':      { name: '文档工程师', icon: '📝', color: '#e8c86a' },
  'general-assistant': { name: '通用助手', icon: '🤖', color: '#a29bfe' },
};

export function ExpertChatPage() {
  const { expertId } = useParams<{ expertId?: string }>();
  const expertInfo = expertId ? EXPERT_INFO[expertId] : null;

  const {
    input,
    setInput,
    streamingUi,
    msgsLoading,
    chatMessages,
    wsStatus,
    handleSend,
    handleSendFile,
    handleStop,
    newChat,
    messagesEndRef,
  } = useChat({ mode: 'expert', expertId });

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--color-bg-deep)' }}>
      {/* ── Top bar ───────────────────────────────────────────── */}
      <header
        className="h-14 md:h-16 flex items-center justify-between relative z-50 p-4 md:px-6 flex-shrink-0"
        style={{
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid var(--color-border-glass)',
        }}
      >
        <div className="flex items-center gap-3 min-w-0">
          {expertInfo ? (
            <>
              <button
                onClick={() => window.history.back()}
                className="flex items-center gap-1.5 text-[13px] text-secondary hover:text-primary transition-colors mr-1"
              >
                <ArrowLeft style={{ width: 16, height: 16 }} />
              </button>
              <div className="flex items-center gap-2">
                <span className="text-[16px]">{expertInfo.icon}</span>
                <div>
                  <h1 className="text-[14px] font-semibold text-primary leading-tight">{expertInfo.name}</h1>
                  <p className="text-[10px] text-secondary mt-0.5 leading-tight">专家模式</p>
                </div>
              </div>
            </>
          ) : (
            <h1 className="text-[15px] font-semibold text-primary truncate">专家</h1>
          )}
          <span
            className={cn(
              'text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider flex items-center gap-1.5',
            )}
            style={{
              color: wsStatus === 'connected' ? 'var(--color-mint)' :
                wsStatus === 'connecting' ? 'var(--color-warning)' : 'var(--color-text-muted)',
              background: wsStatus === 'connected' ? 'rgba(0,255,136,0.08)' :
                wsStatus === 'connecting' ? 'rgba(255,170,51,0.08)' : 'rgba(100,100,200,0.06)',
            }}
          >
            <span className={cn('w-1.5 h-1.5 rounded-full')}
              style={{
                background: wsStatus === 'connected' ? 'var(--color-mint)' :
                  wsStatus === 'connecting' ? 'var(--color-warning)' : 'var(--color-text-muted)',
              }}
            />
            {wsStatus === 'connected' ? 'LIVE' : wsStatus === 'connecting' ? 'SYNC' : 'OFF'}
          </span>
        </div>
      </header>

      {/* ── Content ────────────────────────────────────────────── */}
      <main className="flex flex-col flex-1 min-h-0">
        {chatMessages.length === 0 ? (
          <section className="flex flex-col items-center flex-1 justify-center px-4 pb-16">
            <div
              className="w-18 h-18 rounded-2xl flex items-center justify-center mb-6"
              style={{
                background: 'linear-gradient(135deg, rgba(255,107,107,0.15), rgba(0,240,255,0.1))',
                border: '1px solid rgba(255,107,107,0.15)',
              }}
            >
              <span className="text-3xl">{expertInfo?.icon || '🤖'}</span>
            </div>
            <h2 className="text-2xl font-bold tracking-tight mb-2 text-primary">
              {expertInfo?.name || '专家'} 已就绪
            </h2>
            <p className="text-[13px] mb-8 text-secondary">
              向我提问，我会用专业知识为你解答
            </p>
          </section>
        ) : (
          <section className="flex flex-col flex-1 pt-2 md:pt-4 px-4 md:px-6 pb-4 w-full mx-auto overflow-y-auto">
            <div className="flex-1 space-y-4">
              {msgsLoading ? (
                <div className="space-y-4">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="flex gap-3">
                      <div className="w-7 h-7 rounded-lg skeleton flex-shrink-0" />
                      <div className="space-y-2 flex-1">
                        <div className="skeleton h-4 w-2/3" />
                        <div className="skeleton h-4 w-1/2" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                chatMessages.map((msg) => {
                  const isStreaming = msg.id.startsWith('streaming-') || msg.id.startsWith('sse-');
                  const isThinkingMsg = msg.id.startsWith('thinking-');
                  if (isThinkingMsg) {
                    return <ThinkingBubble key={msg.id} content={msg.reasoning} />;
                  }
                  return (
                    <MessageBubble
                      key={msg.id}
                      role={msg.role as 'user' | 'assistant' | 'tool'}
                      content={msg.content}
                      timestamp={msg.timestamp}
                      isStreaming={isStreaming}
                      reasoning={msg.reasoning}
                      toolCalls={msg.toolCalls}
                    />
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>
          </section>
        )}

        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onSendFile={handleSendFile}
          onStop={handleStop}
          disabled={msgsLoading}
          streaming={streamingUi}
        />
      </main>
    </div>
  );
}
