import { Sparkles, MessageSquare } from 'lucide-react';

interface WelcomeEmptyProps {
  onSuggestionClick: (text: string) => void;
}

const suggestions = [
  { text: '帮我规划一次旅行', icon: '✈️' },
  { text: '推荐几本好书', icon: '📚' },
  { text: '总结今天的新闻要点', icon: '📰' },
  { text: '帮我写一封邮件', icon: '✉️' },
];

export function WelcomeEmpty({ onSuggestionClick }: WelcomeEmptyProps) {
  return (
    <section className="flex flex-col items-center flex-1 justify-center px-4 pb-16">
      {/* Logo */}
      <div
        className="w-18 h-18 rounded-2xl flex items-center justify-center mb-6"
        style={{
          background: 'linear-gradient(135deg, rgba(255,107,107,0.15), rgba(0,240,255,0.1))',
          border: '1px solid rgba(255,107,107,0.15)',
        }}
      >
        <Sparkles className="w-8 h-8" style={{ color: 'var(--color-accent)' }} />
      </div>

      {/* Title */}
      <h2 className="text-2xl font-bold tracking-tight mb-2 text-primary">
        有什么可以帮你？
      </h2>
      <p className="text-[13px] mb-8 text-secondary">
        把问题丢给 EvoGen
      </p>

      {/* Suggestion cards */}
      <div className="grid grid-cols-2 gap-2 w-full max-w-md">
        {suggestions.map((s, i) => (
          <button
            key={i}
            className="flex items-center gap-2 px-3 py-2.5 rounded-[14px] text-[13px] text-left transition-all duration-200 hover:scale-[1.02]"
            style={{
              background: 'var(--color-bg-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-secondary)',
            }}
            onClick={() => onSuggestionClick(s.text)}
          >
            <span className="text-sm flex-shrink-0">{s.icon}</span>
            <span className="truncate">{s.text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
