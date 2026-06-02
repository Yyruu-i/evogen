import { Trash2 } from 'lucide-react';
import { usePersona, useUpdatePersona } from '@/hooks/use-persona';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';
import { Heart } from 'lucide-react';

export function PersonaPreferencesPage() {
  const { data, isLoading } = usePersona();
  const updatePersona = useUpdatePersona();

  // Handle both response shapes: { attributes: { learned_preferences } } or { learned_preferences }
  const attrs: Record<string, unknown> | undefined =
    (data as any)?.attributes || data;
  const prefs: Record<string, unknown> = attrs?.learned_preferences as Record<string, unknown> || {};
  const prefEntries = Object.entries(prefs);

  const formatPrefValue = (value: unknown): string => {
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) return value.map(String).join('、');
    if (value && typeof value === 'object') return JSON.stringify(value, null, 0);
    return String(value ?? '');
  };

  const handleRemove = async (key: string) => {
    const updated = { ...prefs };
    delete updated[key];
    await updatePersona.mutateAsync({ learned_preferences: updated });
  };

  if (isLoading) return <ListSkeleton rows={5} />;

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-1">偏好管理</h3>
      <p className="text-[12px] text-muted mb-4">
        Agent 在对话中自动学习到的偏好。你可以编辑或删除。
      </p>

      {prefEntries.length === 0 ? (
        <EmptyState
          icon={Heart}
          title="暂无学到的偏好"
          description="继续使用 EvoGen，Agent 会逐渐了解你的习惯和偏好。"
        />
      ) : (
        <div className="space-y-2">
          {prefEntries.map(([key, value]) => (
            <div key={key} className="glass-card p-3 flex items-center justify-between">
              <div>
                <p className="text-[13px] font-medium">{key}</p>
                <p className="text-[12px] text-secondary">{formatPrefValue(value)}</p>
              </div>
              <button
                className="p-1.5 rounded hover:bg-hover text-muted hover:text-danger"
                onClick={() => handleRemove(key)}
              >
                <Trash2 style={{ width: 14, height: 14 }} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-6 pt-4 border-t border-color">
        <h4 className="text-[13px] font-medium mb-2">渐进式了解</h4>
        <p className="text-[12px] text-muted">
          已提问 {data?.attributes?.discovery_questions_asked || 0} 个了解性问题。
          Agent 会在对话中自然了解你，无需填问卷。
        </p>
      </div>
    </div>
  );
}
