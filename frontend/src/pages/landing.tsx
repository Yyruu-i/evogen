import { useState, useEffect, useCallback } from 'react';
import { Sparkles, Zap, Brain, Network, MessageSquare, Code2, ChevronRight } from 'lucide-react';

interface Capability {
  id: string;
  icon: typeof Sparkles;
  title: string;
  description: string;
  gradient: string;
}

const capabilities: Capability[] = [
  {
    id: 'multi-agent',
    icon: Network,
    title: '多智能体协作',
    description: '自主编排 AI Agent 团队，并行解决复杂任务',
    gradient: 'from-purple-500/20 to-cyan-500/20',
  },
  {
    id: 'memory',
    icon: Brain,
    title: '持久记忆引擎',
    description: '跨会话记忆存储、检索与进化，越用越懂你',
    gradient: 'from-coral-500/20 to-accent-500/20',
  },
  {
    id: 'skills',
    icon: Zap,
    title: '可扩展技能系统',
    description: '安装社区技能，或创建专属工作流，无限能力边界',
    gradient: 'from-holo-500/20 to-cyan-500/20',
  },
  {
    id: 'code-gen',
    icon: Code2,
    title: '智能代码生成',
    description: '理解上下文，自动编写、审查、重构生产级代码',
    gradient: 'from-accent-500/20 to-purple-500/20',
  },
  {
    id: 'chat',
    icon: MessageSquare,
    title: '自然对话推理',
    description: '深度理解意图，多轮推理，实现真正的智能对话',
    gradient: 'from-cyan-500/20 to-holo-500/20',
  },
];

export function LandingPage({ onEnter }: { onEnter: () => void }) {
  const [activeCap, setActiveCap] = useState(0);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setIsVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveCap((prev) => (prev + 1) % capabilities.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Enter') onEnter();
    },
    [onEnter],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden"      style={{
        background: 'radial-gradient(ellipse 60% 50% at 50% 30%, rgba(20,20,60,0.9) 0%, rgba(5,5,15,0.98) 50%, #05050f 100%)',
      }}>
      {/* Scanline overlay */}
      <div className="scanline" />

      {/* Animated grid particles layer — already in CSS body::before */}

      {/* Floating orbs */}
      <div
        className="absolute w-[600px] h-[600px] rounded-full opacity-[0.06]"
        style={{
          background: 'radial-gradient(circle, var(--color-cyan), transparent 70%)',
          top: '10%',
          left: '20%',
          animation: 'float 8s ease-in-out infinite',
        }}
      />
      <div
        className="absolute w-[400px] h-[400px] rounded-full opacity-[0.05]"
        style={{
          background: 'radial-gradient(circle, var(--color-accent), transparent 70%)',
          bottom: '15%',
          right: '15%',
          animation: 'float 6s ease-in-out infinite 1s',
        }}
      />

      {/* Main content */}
      <div
        className={`relative z-10 flex flex-col items-center gap-8 transition-all duration-1000 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
      >
        {/* Brand mark */}
        <div className="flex flex-col items-center gap-4">
          <div
            className="w-20 h-20 rounded-2xl flex items-center justify-center animate-float"
            style={{
              background: 'linear-gradient(135deg, rgba(255,107,107,0.15), rgba(0,240,255,0.15))',
              border: '1px solid rgba(255,107,107,0.2)',
              boxShadow: '0 0 40px rgba(255,107,107,0.15), 0 0 80px rgba(0,240,255,0.08)',
            }}
          >
            <Sparkles className="w-9 h-9" style={{ color: 'var(--color-accent)' }} />
          </div>

          <h1 className="gradient-text text-[42px] font-bold tracking-tight">
            EvoGen
          </h1>
          <p
            className="text-[15px] tracking-[0.15em] uppercase"
            style={{ color: 'var(--color-text-muted)' }}
          >
            进化灵眸 · Next-Gen Agent Framework
          </p>
        </div>

        {/* Capability carousel */}
        <div className="flex items-center gap-4 h-[120px]">
          {capabilities.map((cap, i) => {
            const Icon = cap.icon;
            const isActive = i === activeCap;
            return (
              <div
                key={cap.id}
                className={`gradient-border rotating-border flex flex-col items-center gap-3 px-5 py-4 rounded-2xl transition-all duration-500 cursor-default ${
                  isActive
                    ? 'scale-110 opacity-100'
                    : 'scale-90 opacity-30'
                }`}
                style={
                  isActive
                    ? {
                        background: 'var(--color-bg-glass)',
                        backdropFilter: 'blur(20px)',
                        boxShadow: '0 0 30px rgba(255,107,107,0.1)',
                      }
                    : {}
                }
              >
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center transition-colors"
                  style={{
                    background: isActive
                      ? 'rgba(255,107,107,0.12)'
                      : 'rgba(100,100,200,0.06)',
                  }}
                >
                  <Icon
                    className="w-5 h-5"
                    style={{
                      color: isActive ? 'var(--color-accent)' : 'var(--color-text-muted)',
                    }}
                  />
                </div>
                <span
                  className="text-[11px] font-semibold tracking-wider uppercase whitespace-nowrap"
                  style={{
                    color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                  }}
                >
                  {cap.title}
                </span>
              </div>
            );
          })}
        </div>

        {/* Carousel indicators */}
        <div className="flex gap-2">
          {capabilities.map((_, i) => (
            <div
              key={i}
              className="h-1 rounded-full transition-all duration-500"
              style={{
                width: i === activeCap ? '24px' : '6px',
                background: i === activeCap
                  ? 'var(--color-accent)'
                  : 'rgba(100,100,200,0.2)',
              }}
            />
          ))}
        </div>

        {/* Active capability description */}
        <p
          className="text-[13px] text-center max-w-sm transition-all duration-500"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {capabilities[activeCap].description}
        </p>

        {/* Enter button */}
        <button
          onClick={onEnter}
          className="btn-primary h-12 px-10 text-[15px] mt-4 animate-pulse-glow neon-pulse group"
        >
          <span>进入 EvoGen</span>
          <ChevronRight
            className="w-4 h-4 transition-transform group-hover:translate-x-1"
          />
        </button>

        <p className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
          按 Enter 快速进入
        </p>
      </div>

      {/* Bottom decorative line */}
      <div
        className="absolute bottom-8 left-1/2 -translate-x-1/2 h-px w-32"
        style={{
          background: 'linear-gradient(90deg, transparent, rgba(255,107,107,0.3), transparent)',
        }}
      />
    </div>
  );
}
