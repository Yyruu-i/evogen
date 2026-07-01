import { useState, useEffect } from 'react';
import { BarChart3, Activity, AlertTriangle, Radio, Shield, Terminal, BookOpen, FileText, RefreshCw } from 'lucide-react';

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

export function StatsPanel() {
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div
      className="rounded-xl p-4 w-full"
      style={{
        background: 'var(--color-bg-glass)',
        backdropFilter: 'blur(24px) saturate(180%)',
        border: '1px solid var(--color-border-glass)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4" style={{ color: 'var(--color-holo)' }} />
          <span className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
            全局统计
          </span>
        </div>
        <button
          onClick={fetchStats}
          className="w-6 h-6 rounded flex items-center justify-center hover:bg-hover transition-colors"
          title="刷新"
        >
          <RefreshCw className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-8 w-full rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <div
          className="text-[11px] p-3 rounded-lg"
          style={{
            background: 'rgba(255,107,107,0.08)',
            color: 'var(--color-red)',
          }}
        >
          {error}
        </div>
      ) : stats ? (
        <div className="space-y-3">
          {/* 概览卡片 */}
          <div className="grid grid-cols-3 gap-1.5">
            <div
              className="flex flex-col items-center py-2 rounded-lg"
              style={{ background: 'rgba(184,192,255,0.06)' }}
            >
              <span className="text-[18px] font-bold" style={{ color: 'var(--color-holo)' }}>
                {stats.totalScans}
              </span>
              <span className="text-[9px] mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                总检测
              </span>
            </div>
            <div
              className="flex flex-col items-center py-2 rounded-lg"
              style={{ background: 'rgba(0,255,136,0.06)' }}
            >
              <span className="text-[18px] font-bold" style={{ color: 'var(--color-mint)' }}>
                {stats.sessionsCount}
              </span>
              <span className="text-[9px] mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                会话
              </span>
            </div>
            <div
              className="flex flex-col items-center py-2 rounded-lg"
              style={{ background: 'rgba(255,215,0,0.06)' }}
            >
              <span className="text-[18px] font-bold" style={{ color: 'var(--color-gold)' }}>
                {stats.artifactsCount}
              </span>
              <span className="text-[9px] mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                制品
              </span>
            </div>
          </div>

          {/* 失败率 */}
          {stats.totalScans > 0 && (
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                失败率
              </span>
              <div className="flex items-center gap-1.5">
                <div className="w-20 h-1.5 rounded-full" style={{ background: 'var(--color-bg-tertiary)' }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(stats.failureRate, 100)}%`,
                      background: stats.failureRate > 20
                        ? 'var(--color-red)'
                        : stats.failureRate > 5
                          ? 'var(--color-gold)'
                          : 'var(--color-mint)',
                    }}
                  />
                </div>
                <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                  {stats.failureRate}%
                </span>
              </div>
            </div>
          )}

          {/* 工具排行 */}
          {stats.toolRanking.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider mb-1.5 px-1" style={{ color: 'var(--color-text-muted)' }}>
                工具使用排行
              </div>
              <div className="space-y-1">
                {stats.toolRanking.map(([toolName, count], idx) => {
                  const Icon = toolIcons[toolName] || Radio;
                  const label = toolLabels[toolName] || toolName;
                  const maxCount = stats.toolRanking[0]?.[1] || 1;
                  return (
                    <div key={toolName} className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-hover transition-colors">
                      <span className="text-[9px] font-mono w-3" style={{ color: 'var(--color-text-muted)' }}>
                        {idx + 1}
                      </span>
                      <Icon className="w-3 h-3 shrink-0" style={{ color: 'var(--color-holo)' }} />
                      <span className="text-[11px] flex-1 truncate">{label}</span>
                      <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                        {count}
                      </span>
                      <div
                        className="h-1.5 rounded-full shrink-0"
                        style={{
                          width: `${(count / maxCount) * 60}px`,
                          background: 'var(--color-holo)',
                          opacity: 0.3 + (count / maxCount) * 0.5,
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!stats.totalScans && !stats.sessionsCount && !stats.artifactsCount && (
            <div className="flex flex-col items-center py-6 gap-2">
              <Activity className="w-8 h-8" style={{ color: 'var(--color-text-muted)' }} />
              <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                暂无统计数据，使用安全工具后将自动记录
              </span>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
