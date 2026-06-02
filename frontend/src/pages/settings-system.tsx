import { useQuery } from '@tanstack/react-query';
import { systemApi } from '@/lib/api';
import { formatUptime } from '@/lib/utils';
import { Skeleton } from '@/components/shared/skeleton';
import { Terminal, CheckCircle } from 'lucide-react';

export function SettingsSystemPage() {
  const { data: health, isLoading } = useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => systemApi.health(),
    refetchInterval: 15000,
  });

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-4">系统状态</h3>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : health ? (
        <div className="space-y-4">
          {/* Health card */}
          <div className="glass-card p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-success/10 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-success" />
              </div>
              <div>
                <p className="text-[14px] font-semibold text-success">系统正常</p>
                <p className="text-[11px] text-muted">Gateway: {health.gateway_status}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-[12px]">
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">运行时间</p>
                <p className="font-mono font-medium">{formatUptime(health.uptime)}</p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">活跃会话</p>
                <p className="font-mono font-medium">{health.sessions}</p>
              </div>
              <div className="bg-tertiary/50 rounded-lg p-3">
                <p className="text-muted mb-0.5">内存使用</p>
                <p className="font-mono font-medium">
                  {health.memory_usage != null ? `${(health.memory_usage / 1024 / 1024).toFixed(1)} MB` : '-'}
                </p>
              </div>
            </div>
          </div>

          {/* Logs */}
          <SystemLogs />
        </div>
      ) : (
        <div className="glass-card p-5 text-center">
          <Terminal className="w-8 h-8 text-muted mx-auto mb-2" />
          <p className="text-[13px] text-muted">无法获取系统状态</p>
          <p className="text-[12px] text-muted">请检查 Gateway 是否正常运行</p>
        </div>
      )}
    </div>
  );
}

function SystemLogs() {
  const { data } = useQuery({
    queryKey: ['system', 'logs'],
    queryFn: () => systemApi.logs({ limit: 20 }),
    staleTime: 30000,
  });

  const logs = data?.logs || [];

  return (
    <div className="glass-card p-5">
      <h4 className="text-[13px] font-medium mb-3">最近日志</h4>
      {logs.length === 0 ? (
        <p className="text-[12px] text-muted">无日志</p>
      ) : (
        <div className="space-y-1.5 max-h-60 overflow-auto font-mono text-[11px]">
          {logs.map((log, i) => (
            <div key={i} className="flex gap-2 text-muted">
              <span className="text-secondary flex-shrink-0">{log.timestamp}</span>
              <span className={`flex-shrink-0 ${
                log.level === 'ERROR' ? 'text-danger' :
                log.level === 'WARN' ? 'text-warning' :
                'text-info'
              }`}>{log.level}</span>
              <span className="truncate">{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
