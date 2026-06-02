import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Brain, Search, Plus, List } from 'lucide-react';
import { useMemoryStats } from '@/hooks/use-memory';
import { LAYER_LABELS } from '@/lib/utils';
import { Skeleton } from '@/components/shared/skeleton';

export function MemoryPage() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { data: stats, isLoading } = useMemoryStats();

  const tabs = [
    { path: '/memory/list', label: '全部记忆' },
    { path: '/memory/search', label: '搜索' },
  ];

  return (
    <div className="flex flex-col min-h-full bg-primary">
      {/* Top bar */}
      <header
        className="h-14 md:h-16 flex items-center justify-between flex-shrink-0 p-4 md:px-6"
        style={{
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid var(--color-border-glass)',
        }}
      >
        <div className="flex items-center gap-3">
          <Brain className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h1 className="text-[15px] font-semibold text-primary">记忆浏览器</h1>
          {stats && (
            <span className="text-[12px] text-muted">
              {stats.total_facts} 条记忆
            </span>
          )}
        </div>
        <button
          className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-lg text-secondary hover:text-primary hover:bg-hover transition-colors"
          onClick={() => navigate('/memory/list')}
        >
          <Plus style={{ width: 14, height: 14 }} />
          添加记忆
        </button>
      </header>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-4 md:px-6 pb-2 border-b border-color">
        {tabs.map(({ path, label }) => (
          <button
            key={path}
            onClick={() => navigate(path)}
            className={`px-4 py-2 text-[13px] font-medium rounded-lg transition-colors ${
              pathname.startsWith(path)
                ? 'text-primary'
                : 'text-secondary hover:text-primary'
            }`}
            style={pathname.startsWith(path) ? { background: 'var(--color-tab-active)' } : {}}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Stats bar */}
      {isLoading ? (
        <div className="px-6 py-3"><Skeleton className="h-8 w-48" /></div>
      ) : stats ? (
        <div className="flex items-center gap-4 px-6 py-3 text-[12px] text-secondary border-b border-color">
          {Object.entries(stats.by_layer).map(([layer, count]) => (
            <span key={layer}>
              {LAYER_LABELS[layer] || layer}: <strong className="text-primary">{count}</strong>
            </span>
          ))}
        </div>
      ) : null}

      {/* Content */}
      <main className="flex flex-col flex-1">
        <section className="flex flex-col flex-1 pt-4 px-4 md:px-6 pb-8 max-w-4xl mx-auto w-full">
          <Outlet />
        </section>
      </main>
    </div>
  );
}
