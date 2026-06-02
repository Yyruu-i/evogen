import { type LucideIcon } from 'lucide-react';

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 animate-float"
        style={{ background: 'var(--color-accent-subtle)' }}
      >
        <Icon className="w-8 h-8 text-accent" />
      </div>
      <h3 className="text-[15px] font-semibold mb-1.5">{title}</h3>
      {description && (
        <p className="text-[13px] text-secondary max-w-64 mb-4">{description}</p>
      )}
      {action && (
        <button className="btn-primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
