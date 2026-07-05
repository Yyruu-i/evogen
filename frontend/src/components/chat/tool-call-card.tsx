import { useState, useEffect, useRef, useMemo } from 'react';
import { Wrench, CheckCircle, XCircle, Clock, ChevronDown, ChevronRight, ChevronUp, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ToolCallInfo {
  callId: string;
  toolName: string;
  args: string;
  result?: string;
  costTime?: number;
  errorMsg?: string;
  success?: boolean;
  timestamp?: number;
}

interface ToolCallCardProps {
  call: ToolCallInfo;
}

function formatArgs(argsStr: string): string {
  try {
    const parsed = JSON.parse(argsStr);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return argsStr;
  }
}

function formatCost(ms?: number): string {
  if (!ms) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * 从 args JSON 中提取 target/IP 字段
 */
function extractTargetFromArgs(argsStr: string): string | null {
  try {
    const parsed = JSON.parse(argsStr);
    return parsed.target || parsed.host || parsed.ip || null;
  } catch {
    return null;
  }
}

/**
 * 判断该工具是否支持进度查询
 */
function supportsProgress(toolName: string): boolean {
  return toolName === 'security_scan' || toolName === 'port_scan_target' || toolName === 'port_scan';
}

/**
 * 获取 API base URL（与前端页面相同的 origin）
 */
function getApiBase(): string {
  return `${window.location.protocol}//${window.location.host}`;
}

/**
 * 专用于 security_scan / port_scan_target 的进度轮询 hook
 * 工具执行期间（!success && !errorMsg）轮询进度 API
 */
function useProgressPolling(toolName: string, args: string, finished: boolean) {
  const [progress, setProgress] = useState<{ stage: string; detail: string; percent: number } | null>(null);
  const target = useMemo(() => extractTargetFromArgs(args), [args]);

  useEffect(() => {
    // 只在支持进度查询且工具尚未结束时轮询
    if (!supportsProgress(toolName) || !target || finished) {
      setProgress(null);
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch(`${getApiBase()}/api/v1/agent/scan-progress/${encodeURIComponent(target)}`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setProgress(data);
          }
        }
      } catch {
        // 忽略网络错误，静默重试
      }
    };

    // 立即执行一次
    poll();

    // 每 1 秒轮询一次
    const interval = setInterval(poll, 1000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [toolName, target, finished]);

  return progress;
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isSuccess = call.success !== false;
  // 工具是否仍在执行中（未完成）
  const isInProgress = !call.result && !call.errorMsg && call.success === undefined;
  // 进度轮询
  const progress = useProgressPolling(call.toolName, call.args, !isInProgress);

  // 进度百分比颜色
  const progressColor =
    progress && progress.percent >= 95
      ? 'var(--color-mint)'
      : progress && progress.percent >= 50
        ? 'var(--color-accent)'
        : 'var(--color-warning)';

  return (
    <div
      className="rounded-2xl overflow-hidden text-[13px]"
      style={{
        background: 'var(--chat-bubble-assistant)',
        border: '1px solid var(--chat-bubble-assistant-border)',
        boxShadow: 'var(--chat-bubble-shadow)',
      }}
    >
      {/* ── Header ── */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 px-3.5 py-2.5 w-full text-left select-none hover:opacity-80 transition-all"
        style={{ color: 'var(--color-text-primary)' }}
      >
        {isInProgress ? (
          <Loader2 className="w-3.5 h-3.5 flex-shrink-0 animate-spin" style={{ color: 'var(--color-accent)' }} />
        ) : (
          <Wrench className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
        )}
        <span className="font-semibold text-[13px] flex-1">{call.toolName}</span>

        {/* ── 进度显示 ── */}
        {isInProgress && progress && (
          <span
            className="flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-full"
            style={{
              background: 'rgba(255,170,51,0.1)',
              color: 'var(--color-warning)',
            }}
          >
            {progress.percent}%
          </span>
        )}

        {call.costTime && (
          <span className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
            <Clock className="w-3 h-3" />
            {formatCost(call.costTime)}
          </span>
        )}
        {isInProgress ? (
          <span
            className="w-3.5 h-3.5 flex items-center justify-center"
            style={{ color: 'var(--color-warning)' }}
          >
            <Clock className="w-3.5 h-3.5 animate-pulse" />
          </span>
        ) : isSuccess ? (
          <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-mint)' }} />
        ) : (
          <XCircle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-coral)' }} />
        )}
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
        )}
      </button>

      {/* ── 进度条（仅执行中且可见） ── */}
      {isInProgress && progress && (
        <div className="px-3.5 pb-2">
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ background: 'var(--color-border-glass)' }}
          >
            <div
              className="h-full rounded-full transition-all duration-500 ease-out"
              style={{
                width: `${Math.min(100, progress.percent)}%`,
                background: progressColor,
              }}
            />
          </div>
          <div
            className="mt-1 text-[10px] leading-tight truncate"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {progress.stage}{progress.detail ? ` — ${progress.detail}` : ''}
          </div>
        </div>
      )}

      {/* ── Expanded details ── */}
      {expanded && (
        <div
          className="px-3.5 py-2.5 flex flex-col gap-2.5"
          style={{
            borderTop: '1px solid var(--color-border-glass)',
            color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
          }}
        >
          {/* Parameters */}
          <div>
            <div className="font-medium text-[11px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Parameters
            </div>
            <pre className="whitespace-pre-wrap break-all leading-relaxed bg-black/10 dark:bg-black/20 rounded-lg p-2.5 overflow-x-auto">
              {formatArgs(call.args)}
            </pre>
          </div>

          {/* Error (if any) */}
          {call.errorMsg && !isSuccess && (
            <div>
              <div className="font-medium text-[11px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-coral)' }}>
                Error
              </div>
              <pre className="whitespace-pre-wrap break-all leading-relaxed bg-black/10 dark:bg-black/20 rounded-lg p-2.5 overflow-x-auto" style={{ color: 'var(--color-coral)' }}>
                {call.errorMsg}
              </pre>
            </div>
          )}

          {/* Result (if success) */}
          {call.result && isSuccess && (
            <div>
              <div className="font-medium text-[11px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                Result
              </div>
              <pre className="whitespace-pre-wrap break-all leading-relaxed bg-black/10 dark:bg-black/20 rounded-lg p-2.5 overflow-x-auto max-h-40 overflow-y-auto">
                {call.result}
              </pre>
            </div>
          )}

          {/* 进度详情（展开时完整显示） */}
          {progress && (
            <div>
              <div className="font-medium text-[11px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                Progress
              </div>
              <div className="whitespace-pre-wrap break-all leading-relaxed bg-black/10 dark:bg-black/20 rounded-lg p-2.5 overflow-x-auto flex items-center gap-2">
                <div
                  className="h-2 rounded-full flex-1 overflow-hidden"
                  style={{ background: 'var(--color-border-glass)' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-500 ease-out"
                    style={{
                      width: `${Math.min(100, progress.percent)}%`,
                      background: progressColor,
                    }}
                  />
                </div>
                <span className="text-[11px] font-semibold whitespace-nowrap">{progress.percent}%</span>
              </div>
              {progress.detail && (
                <div className="mt-1 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                  {progress.detail}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
