import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Wrench } from 'lucide-react';

export function SkillsPage() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const tabs = [
    { path: '/skills/local', label: '本地技能' },
    { path: '/skills/hub', label: '技能市场' },
  ];

  return (
    <div className="flex flex-col min-h-full bg-primary">
      <header
        className="h-14 md:h-16 flex items-center flex-shrink-0 p-4 md:px-6"
        style={{
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid var(--color-border-glass)',
        }}
      >
        <div className="flex items-center gap-3">
          <Wrench className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h1 className="text-[15px] font-semibold text-primary">技能管理</h1>
        </div>
      </header>

      <div className="flex items-center gap-1 px-4 md:px-6 pb-2 border-b border-color">
        {tabs.map(({ path, label }) => (
          <button
            key={path}
            onClick={() => navigate(path)}
            className={`px-4 py-2 text-[13px] font-medium rounded-lg transition-colors ${
              pathname === path ? 'text-primary' : 'text-secondary hover:text-primary'
            }`}
            style={pathname === path ? { background: 'var(--color-tab-active)' } : {}}
          >
            {label}
          </button>
        ))}
      </div>

      <main className="flex flex-col flex-1">
        <section className="flex flex-col flex-1 pt-4 px-4 md:px-6 pb-8 max-w-4xl mx-auto w-full">
          <Outlet />
        </section>
      </main>
    </div>
  );
}
