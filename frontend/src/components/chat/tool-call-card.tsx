import { useState } from 'react';
import { Wrench, CheckCircle, XCircle, Clock, ChevronDown, ChevronRight, ChevronUp } from 'lucide-react';
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

export function ToolCallCard({ call }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isSuccess = call.success !== false;

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
        <Wrench className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
        <span className="font-semibold text-[13px] flex-1">{call.toolName}</span>
        {call.costTime && (
          <span className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
            <Clock className="w-3 h-3" />
            {formatCost(call.costTime)}
          </span>
        )}
        {isSuccess ? (
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
        </div>
      )}
    </div>
  );
}
