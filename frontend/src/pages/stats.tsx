import { useState, useEffect } from 'react';
import {
  BarChart3, Activity, AlertTriangle, Radio, Shield, Terminal,
  RefreshCw, FileText, MessageSquare, ArrowUpRight,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface ScanStats {
  port_scan: number;
  vuln_scan: number;
  rkhunter_scan: number;
  chkrootkit_scan: number;
}

interface GlobalStats {
  scanStats: ScanStats;
  totalScans: number;
  totalFailures: number;
  failureRate: number;
  sessionsCount: number;
  artifactsCount: number;
  toolRanking: [string, number][];
}

const toolIcons: Record<string, typeof Shield> = {
  port_scan: Activity,
  vuln_scan: AlertTriangle,
  rkhunter_scan: Shield,
  chkrootkit_scan: Terminal,
};

const toolLabels: Record<string, string> = {
  port_scan: '端口扫描',
  vuln_scan: '漏洞扫描',
  rkhunter_scan: 'Rootkit 检测',
  chkrootkit_scan: 'Chkrootkit 扫描',
};

function StatCard({ label, value, icon: Icon, color, bg }: {
  label: string;
  value: number | string;
  icon: typeof BarChart3;
  color: string;
  bg: string;
}) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{ background: bg, border: `1px solid ${color}20` }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-muted)' }}>
          {label}
        </span>
        <Icon className="w-4 h-4" style={{ color }} />
      </div>
      <span className="text-[28px] font-bold" style={{ color }}>
        {value}
      </span>
    </div>
  );
}

export function StatsPage() {
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const fetchStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = (() => { try { return localStorage.getItem('evogen-auth-token') || ''; } catch { return ''; } })();
      const res = await fetch('/api/v1/system/stats', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setStats(json.data || json);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  return (
    <div className="h-full overflow-y-auto p-6" style={{ background: 'var(--color-bg-deep)' }}>
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-5 h-5" style={{ color: 'var(--color-holo)' }} />
            <h1 className="text-[18px] font-bold text-primary">全局统计</h1>
          </div>
          <button
            onClick={fetchStats}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-lg transition-all text-secondary hover:text-primary hover:bg-hover"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>

        {loading && !stats ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton h-24 w-full rounded-xl" />
            ))}
          </div>
        ) : error ? (
          <div
            className="p-4 rounded-xl text-[13px]"
            style={{
              background: 'rgba(255,107,107,0.08)',
              color: 'var(--color-red)',
              border: '1px solid rgba(255,107,107,0.2)',
            }}
          >
            {error}
          </div>
        ) : stats ? (
          <>
            {/* 概览卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="总检测次数"
                value={stats.totalScans}
                icon={Radio}
                color="var(--color-holo)"
                bg="rgba(184,192,255,0.06)"
              />
              <StatCard
                label="会话数"
                value={stats.sessionsCount}
                icon={MessageSquare}
                color="var(--color-mint)"
                bg="rgba(0,255,136,0.06)"
              />
              <StatCard
                label="制品数"
                value={stats.artifactsCount}
                icon={FileText}
                color="var(--color-gold)"
                bg="rgba(255,215,0,0.06)"
              />
              <StatCard
                label="失败率"
                value={`${stats.failureRate}%`}
                icon={AlertTriangle}
                color={stats.failureRate > 20 ? 'var(--color-red)' : stats.failureRate > 5 ? 'var(--color-gold)' : 'var(--color-mint)'}
                bg={stats.failureRate > 20 ? 'rgba(255,107,107,0.06)' : stats.failureRate > 5 ? 'rgba(255,215,0,0.06)' : 'rgba(0,255,136,0.06)'}
              />
            </div>

            {/* 工具使用排行 */}
            <div
              className="rounded-xl p-5"
              style={{
                background: 'var(--color-bg-glass)',
                backdropFilter: 'blur(24px) saturate(180%)',
                border: '1px solid var(--color-border-glass)',
              }}
            >
              <h2 className="text-[13px] font-semibold mb-4 text-primary">工具使用排行</h2>
              {stats.toolRanking.length > 0 ? (
                <div className="space-y-2">
                  {stats.toolRanking.map(([toolName, count], idx) => {
                    const Icon = toolIcons[toolName] || Radio;
                    const label = toolLabels[toolName] || toolName;
                    const maxCount = stats.toolRanking[0]?.[1] || 1;
                    const pct = count / maxCount;
                    return (
                      <div key={toolName} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-hover transition-colors">
                        <span
                          className="text-[11px] font-mono w-5 text-center font-bold"
                          style={{
                            color: idx === 0 ? 'var(--color-gold)' : idx === 1 ? 'var(--color-text-secondary)' : idx === 2 ? 'var(--color-warning)' : 'var(--color-text-muted)',
                          }}
                        >
                          {idx + 1}
                        </span>
                        <Icon className="w-4 h-4 shrink-0" style={{ color: 'var(--color-holo)' }} />
                        <span className="text-[13px] flex-1 truncate text-primary">{label}</span>
                        <span className="text-[12px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                          {count} 次
                        </span>
                        <div className="w-32 h-2 rounded-full shrink-0" style={{ background: 'var(--color-bg-tertiary)' }}>
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${pct * 100}%`,
                              background: idx === 0
                                ? 'linear-gradient(90deg, var(--color-gold), var(--color-holo))'
                                : 'var(--color-holo)',
                              opacity: 0.3 + pct * 0.5,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center py-8 gap-2">
                  <Activity className="w-8 h-8" style={{ color: 'var(--color-text-muted)' }} />
                  <span className="text-[12px]" style={{ color: 'var(--color-text-muted)' }}>
                    暂无检测记录
                  </span>
                  <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                    使用安全扫描工具后，数据将自动记录在此
                  </span>
                </div>
              )}
            </div>

            {/* 快捷操作 */}
            <div className="flex gap-3">
              <button
                onClick={() => navigate('/chat')}
                className="flex items-center gap-2 px-4 py-2.5 text-[12px] font-medium rounded-xl transition-all hover:opacity-80"
                style={{
                  background: 'rgba(184,192,255,0.08)',
                  color: 'var(--color-holo)',
                  border: '1px solid rgba(184,192,255,0.15)',
                }}
              >
                <MessageSquare className="w-4 h-4" />
                开始新检测
                <ArrowUpRight className="w-3 h-3" />
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
