import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/auth-context';
import { useWsStatus } from '@/context/ws-context';
import {
  MessageSquare,
  Brain,
  BookOpen,
  UserCircle,
  Wrench,
  Settings,
  Sparkles,
  Hash,
  Plus,
  ChevronDown,
  ChevronRight,
  Layers,
  Cpu,
  Zap,
  LogOut,
} from 'lucide-react';
import { ThemeToggle } from '@/components/shared/theme-toggle';
import { useSessions } from '@/hooks/use-sessions';
import { cn } from '@/lib/utils';
import type { WsStatus } from '@/context/ws-context';

/* ── WS status badge (shared between header & sidebar) ──────── */
function WsStatusBadge() {
  const { wsStatus } = useWsStatus();
  const statusConfig: Record<WsStatus, { label: string; color: string; bg: string }> = {
    connected: { label: 'ONLINE', color: 'var(--color-mint)', bg: 'rgba(0,255,136,0.08)' },
    connecting: { label: 'SYNC', color: 'var(--color-warning)', bg: 'rgba(255,170,51,0.08)' },
    disconnected: { label: 'OFF', color: 'var(--color-text-muted)', bg: 'rgba(100,100,200,0.06)' },
  };
  const { label, color, bg } = statusConfig[wsStatus];
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded font-mono" style={{ background: bg, color }}>
      {label}
    </span>
  );
}

/* ── DeerFlow-style navigation sections ───────────────────────── */
interface NavSection {
  id: string;
  label: string;
  icon: typeof MessageSquare;
  items: { to: string; icon: typeof MessageSquare; label: string; badge?: string }[];
}

export function Sidebar() {
  const navigate = useNavigate();
  const auth = useAuth();
  const { data } = useSessions({ limit: 30 });
  const sessions = data?.sessions || [];
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    agent: true,
    resource: true,
    system: false,
  });

  const toggleSection = (id: string) => {
    setExpandedSections((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  /* ── Navigation sections (DeerFlow hierarchy + LightRAG modules) ── */
  const sections: NavSection[] = [
    {
      id: 'agent',
      label: 'Agent',
      icon: Cpu,
      items: [
        { to: '/chat', icon: MessageSquare, label: '对话' },
        { to: '/persona/attributes', icon: UserCircle, label: '人格' },
      ],
    },
    {
      id: 'resource',
      label: '资源库',
      icon: Layers,
      items: [
        { to: '/skills/local', icon: Wrench, label: '技能' },
        { to: '/tools', icon: Zap, label: '工具' },
        { to: '/experience/list', icon: BookOpen, label: '经验' },
        { to: '/memory/list', icon: Brain, label: '记忆' },
        { to: '/knowledge', icon: BookOpen, label: '知识库' },
      ],
    },
    {
      id: 'system',
      label: '系统',
      icon: Settings,
      items: [
        { to: '/settings/models', icon: Settings, label: '设置' },
      ],
    },
  ];

  return (
    <aside
      className="glass hidden md:flex h-full shrink-0 flex-col overflow-hidden relative z-20"
      style={{
        width: 'var(--sidebar-width)',
        background: 'var(--color-bg-glass)',
        backdropFilter: 'blur(24px) saturate(180%)',
        WebkitBackdropFilter: 'blur(24px) saturate(180%)',
        borderRight: '1px solid var(--color-border-glass)',
      }}
    >
      {/* ── Brand header ──────────────────────────────────────── */}
      <div className="flex shrink-0 items-center h-14 px-3">
        <button
          className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl hover:bg-hover transition-all duration-200 w-full group"
          onClick={() => navigate('/chat')}
        >
          <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-all duration-200 group-hover:shadow-[0_0_16px_rgba(255,107,107,0.25)] group-hover:scale-105"
          style={{ background: 'rgba(255,107,107,0.12)' }}
          >
            <Sparkles className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
          </div>
          <span className="text-[15px] font-bold tracking-tight text-primary">
            EvoGen
          </span>
        </button>
      </div>

      {/* ── Separator ─────────────────────────────────────────── */}
      <div className="mx-3 h-px shrink-0" style={{ background: 'var(--color-border-glass)' }} />

      {/* ── Navigation sections (collapsible) ──────────────────── */}
      <nav className="flex shrink-0 flex-col gap-1 p-2 overflow-y-auto custom-scrollbar">
        {sections.map((section) => {
          const SectionIcon = section.icon;
          const expanded = expandedSections[section.id];
          return (
            <div key={section.id} className="mb-0.5">
              {/* Section header */}
              <button
                onClick={() => toggleSection(section.id)}
                className="flex items-center w-full h-8 px-2.5 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all duration-200 hover:bg-[var(--color-bg-hover)] hover:text-primary"
                style={{ color: 'var(--color-text-muted)' }}
              >
                <SectionIcon className="w-3.5 h-3.5 mr-2" />
                <span className="flex-1 text-left">{section.label}</span>
                {expanded ? (
                  <ChevronDown className="w-3 h-3 transition-transform duration-200" />
                ) : (
                  <ChevronRight className="w-3 h-3 transition-transform duration-200" />
                )}
              </button>

              {/* Section items */}
              <div
                className={cn(
                  'overflow-hidden transition-all duration-300 ease-out',
                  expanded ? 'max-h-56 opacity-100 mt-0.5' : 'max-h-0 opacity-0',
                )}
              >
                {section.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/chat'}
                      className={({ isActive }) =>
                        cn(
                          'flex items-center h-9 rounded-lg transition-all duration-200 w-full gap-2.5 px-2.5 ml-4',
                          isActive
                            ? 'text-primary font-medium'
                            : 'text-secondary hover:text-primary hover:bg-[var(--color-bg-hover)]',
                        )
                      }
                      style={({ isActive }) =>
                        isActive
                          ? {
                              background: 'rgba(255,107,107,0.08)',
                              borderLeft: '2px solid var(--color-accent)',
                              boxShadow: 'inset 0 0 0 1px rgba(255,107,107,0.06)',
                            }
                          : { borderLeft: '2px solid transparent' }
                      }
                    >
                      <div className="flex size-7 shrink-0 items-center justify-center rounded-md">
                        <Icon style={{ width: 16, height: 16 }} />
                      </div>
                      <span className="text-[12px] truncate flex-1 min-w-0 text-left">
                        {item.label}
                      </span>
                      {item.badge && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold"
                          style={{
                            background: 'rgba(255,107,107,0.12)',
                            color: 'var(--color-accent)',
                          }}
                        >
                          {item.badge}
                        </span>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {/* ── Separator ─────────────────────────────────────────── */}
      <div className="mx-3 h-px shrink-0 my-1" style={{ background: 'var(--color-border-glass)' }} />

      {/* ── Recent conversations ───────────────────────────────── */}
      <div className="flex flex-col min-h-0 flex-1 transition-opacity duration-300 opacity-100">
        <div className="shrink-0 flex items-center px-3 py-1.5 mx-2 mt-1">
          <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-muted)' }}>
            最近对话
          </span>
        </div>

        <div className="flex flex-col flex-1 min-h-0 overflow-y-auto pl-2 pr-0.5 custom-scrollbar">
          <div className="flex flex-col flex-1 gap-0.5">
            {sessions.length === 0 ? (
              <div
                className="mx-2 flex flex-col items-center gap-2 rounded-xl px-3 py-4 transition-colors duration-200"
                style={{ border: '1px dashed rgba(100,100,200,0.1)' }}
              >
                <Hash className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
                <span className="text-[11px] text-center" style={{ color: 'var(--color-text-muted)' }}>
                  暂无对话
                </span>
              </div>
            ) : (
              sessions.slice(0, 20).map((s) => (
                <button
                  key={s.id}
                  onClick={() => navigate(`/chat?session=${s.id}`)}
                  title={s.title || '新对话'}
                  className="group/item flex items-center h-9 w-full rounded-lg transition-all duration-200 cursor-pointer hover:bg-[var(--color-bg-hover)] active:scale-[0.98] px-2.5 gap-2.5"
                >
                  <div className="flex size-7 shrink-0 items-center justify-center transition-transform duration-200 group-hover/item:scale-110">
                    <MessageSquare className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                  </div>
                  <span
                    className="text-[12px] font-medium truncate flex-1 min-w-0 text-left group-hover/item:text-primary transition-colors duration-200"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {s.title || '新对话'}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <div
        className="shrink-0 flex items-center justify-between px-3 py-3"
        style={{ borderTop: '1px solid var(--color-border-glass)' }}
      >
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {auth.user ? (
            <>
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--color-accent)' }}
              >
                <span className="text-[10px] font-bold text-white">
                  {auth.user.username.charAt(0).toUpperCase()}
                </span>
              </div>
              <span
                className="text-[11px] font-medium truncate"
                style={{ color: 'var(--color-text-secondary)' }}
                title={auth.user.username}
              >
                {auth.user.username}
              </span>
            </>
          ) : (
            <>
              <span className="relative flex h-2 w-2">
                <span
                  className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                  style={{ background: 'var(--color-mint)' }}
                />
                <span
                  className="relative inline-flex rounded-full h-2 w-2"
                  style={{ background: 'var(--color-mint)' }}
                />
              </span>
              <span className="text-[10px] font-mono tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
                v1.0
              </span>
              <WsStatusBadge />
            </>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <ThemeToggle />
          <button
            onClick={() => { auth.logout(); navigate('/login'); }}
            className="theme-toggle"
            title="登出"
          >
            <LogOut style={{ width: 14, height: 14 }} />
          </button>
        </div>
      </div>
    </aside>
  );
}
