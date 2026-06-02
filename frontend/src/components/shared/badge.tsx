import { cn } from '@/lib/utils';
import { type ReactNode } from 'react';

export function Badge({
  children,
  variant = 'default',
  className,
}: {
  children: ReactNode;
  variant?: 'default' | 'success' | 'danger' | 'warning' | 'info' | 'accent';
  className?: string;
}) {
  const colors: Record<string, string> = {
    default: 'bg-tertiary text-secondary',
    success: 'text-success',
    danger: 'text-danger',
    warning: 'text-warning',
    info: 'text-info',
    accent: 'text-accent',
  };

  return (
    <span
      className={cn(
        'badge',
        colors[variant],
        variant !== 'default' && 'bg-transparent',
        className,
      )}
      style={
        variant !== 'default'
          ? { background: `var(--color-${variant === 'accent' ? 'accent' : variant}-subtle)` }
          : undefined
      }
    >
      {children}
    </span>
  );
}
