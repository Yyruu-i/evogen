import { useQuery } from '@tanstack/react-query';
import { systemApi } from '@/lib/api';
import { Skeleton } from '@/components/shared/skeleton';
import { Terminal, CheckCircle, XCircle, Database } from 'lucide-react';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function SettingsSystemPage() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['system', 'status'],
    queryFn: () => systemApi.status(),
    refetchInterval: 15000,
  });

  const { data: capacity } = useQuery({
    queryKey: ['system', 'capacity'],
    queryFn: () => systemApi.capacity(),
    staleTime: 30000,
  });

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-4">系统状态</h3>

      <div className="space-y-4">
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : status ? (
          /* System status card */
          <div className="glass-card p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                status.agent.status === 'online' ? 'bg-success/10' : 'bg-danger/10'
              }`}>
                {status.agent.status === 'online' ? (
                  <CheckCircle className="w-5 h-5 text-success" />
                ) : (
                  <XCircle className="w-5 h-5 text-danger" />
                )}
              </div>
              <div>
                <p className={`text-[14px] font-semibold ${
                  status.agent.status === 'online' ? 'text-success' : 'text-danger'
                }`}>
                  Agent {status.agent.status === 'online' ? '在线' : '离线'}
                </p>
                <p className="text-[11px] text-muted">
                  v{status.agent.version} · {status.agent.uptime_human}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-[12px]">
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">Gateway</p>
                <p className={`font-mono font-medium ${
                  status.gateway.running ? 'text-success' : 'text-danger'
                }`}>
                  {status.gateway.running
                    ? `${status.gateway.profiles.length} profiles`
                    : status.gateway.error || '未运行'}
                </p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">数据库</p>
                <p className={`font-mono font-medium ${
                  status.database.connected ? 'text-success' : 'text-danger'
                }`}>
                  {status.database.connected
                    ? `${status.database.memory_facts} 条记忆`
                    : status.database.error || '未连接'}
                </p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">Python</p>
                <p className="font-mono font-medium">{status.agent.python_version}</p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">启动时间</p>
                <p className="font-mono font-medium text-[11px]">
                  {new Date(status.agent.started_at).toLocaleString('zh-CN', {
                    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                  })}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="glass-card p-5 text-center">
            <Terminal className="w-8 h-8 text-muted mx-auto mb-2" />
            <p className="text-[13px] text-muted">无法获取系统状态</p>
            <p className="text-[12px] text-muted">请检查 Gateway 是否正常运行</p>
          </div>
        )}

        {/* Storage capacity card (independent) */}
        {capacity && (
          <div className="glass-card p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
                <Database className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
              </div>
              <div>
                <p className="text-[14px] font-semibold">存储用量</p>
                <p className="text-[11px] text-muted">
                  已用 {capacity.usage_percent.toFixed(1)}% · {capacity.total_facts} 条记忆
                </p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="mb-3">
              <div className="flex justify-between text-[11px] text-muted mb-1">
                <span>{formatBytes(capacity.storage_estimate_bytes)}</span>
                <span>{capacity.capacity_limit.toLocaleString()} 条上限</span>
              </div>
              <div className="h-2 rounded-full bg-tertiary/50 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.min(capacity.usage_percent, 100)}%`,
                    background: capacity.usage_percent > 80
                      ? 'var(--color-danger)'
                      : capacity.usage_percent > 50
                        ? 'var(--color-warning)'
                        : 'var(--color-accent)',
                  }}
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 text-[12px]">
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">向量存储</p>
                <p className="font-mono font-medium">{formatBytes(capacity.total_vector_bytes)}</p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">总占用</p>
                <p className="font-mono font-medium">{formatBytes(capacity.storage_estimate_bytes)}</p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">记忆总数</p>
                <p className="font-mono font-medium">{capacity.total_facts}</p>
              </div>
            </div>
          </div>
        )}

        {/* System logs */}
        <SystemLogs />
      </div>
    </div>
  );
}

function SystemLogs() {
  const { data } = useQuery({
    queryKey: ['system', 'logs'],
    queryFn: () => systemApi.logs({ limit: 50 }),
    staleTime: 30000,
  });

  const entries = data?.entries || [];
  const total = data?.total ?? entries.length;

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-[13px] font-medium">最近日志</h4>
        {total > 0 && (
          <span className="text-[11px] text-muted">共 {total} 条</span>
        )}
      </div>
      {entries.length === 0 ? (
        <p className="text-[12px] text-muted">无日志</p>
      ) : (
        <div className="space-y-1 max-h-60 overflow-auto font-mono text-[11px]">
          {entries.map((entry, i) => (
            <div key={i} className="flex gap-2 text-muted hover:bg-hover/50 rounded px-1 py-0.5 -mx-1">
              {entry.timestamp ? (
                <span className="text-secondary flex-shrink-0">{entry.timestamp.split(',')[0]}</span>
              ) : (
                <span className="text-secondary flex-shrink-0 opacity-50">--:--</span>
              )}
              <span className={`flex-shrink-0 font-semibold ${
                entry.level === 'ERROR' || entry.level === 'CRITICAL' ? 'text-danger' :
                entry.level === 'WARNING' ? 'text-warning' :
                'text-info'
              }`}>{entry.level}</span>
              <span className="truncate">{entry.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
