import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Trash2, Star } from 'lucide-react';
import { useMemoryFact, useUpdateMemory, useDeleteMemory } from '@/hooks/use-memory';
import { LAYER_LABELS, FACT_TYPE_LABELS, formatDate } from '@/lib/utils';
import { Badge } from '@/components/shared/badge';
import { Skeleton } from '@/components/shared/skeleton';
import { useState } from 'react';

export function MemoryDetailPage() {
  const { factId } = useParams<{ factId: string }>();
  const navigate = useNavigate();
  const { data: fact, isLoading } = useMemoryFact(factId || '');
  const updateMemory = useUpdateMemory();
  const deleteMemory = useDeleteMemory();
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');

  if (isLoading) {
    return (
      <div className="max-w-2xl space-y-4 p-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (!fact) {
    return <p className="text-muted p-4">记忆不存在或已删除。</p>;
  }

  const handleDelete = async () => {
    await deleteMemory.mutateAsync(fact.id);
    navigate('/memory/list');
  };

  const handleSave = async () => {
    await updateMemory.mutateAsync({ id: fact.id, updates: { content: editContent } });
    setEditing(false);
  };

  const handleReinforce = async () => {
    await updateMemory.mutateAsync({
      id: fact.id,
      updates: { importance: Math.min(1, fact.importance + 0.1), layer: fact.layer === 'working' ? 'core' : fact.layer },
    });
  };

  return (
    <div className="max-w-2xl">
      <button
        className="btn-ghost mb-4 h-7 text-[12px]"
        onClick={() => navigate('/memory/list')}
      >
        <ArrowLeft style={{ width: 14, height: 14 }} />
        返回
      </button>

      <div className="glass-card p-6 space-y-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Badge variant={
              fact.type === 'preference' ? 'info' :
              fact.type === 'procedure' ? 'accent' :
              fact.type === 'relationship' ? 'warning' : 'default'
            }>
              {FACT_TYPE_LABELS[fact.type] || fact.type}
            </Badge>
            <span className="text-[12px] text-secondary">{LAYER_LABELS[fact.layer]}</span>
          </div>
          <div className="flex gap-1">
            <button className="btn-ghost h-7 w-7 p-0 flex items-center justify-center" onClick={handleReinforce} title="提升为核心记忆">
              <Star style={{ width: 14, height: 14, color: fact.layer === 'core' ? 'var(--color-amber)' : undefined }} />
            </button>
            <button className="btn-ghost h-7 w-7 p-0 flex items-center justify-center text-danger" onClick={handleDelete}>
              <Trash2 style={{ width: 14, height: 14 }} />
            </button>
          </div>
        </div>

        {editing ? (
          <div className="space-y-3">
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={3}
              className="w-full"
            />
            <div className="flex gap-2">
              <button className="btn-primary h-7 text-[12px]" onClick={handleSave}>保存</button>
              <button className="btn-ghost h-7 text-[12px]" onClick={() => setEditing(false)}>取消</button>
            </div>
          </div>
        ) : (
          <p
            className="text-[14px] leading-relaxed cursor-pointer hover:bg-tertiary/50 rounded p-1 -m-1 transition-colors"
            onClick={() => { setEditContent(fact.content); setEditing(true); }}
          >
            {fact.content}
          </p>
        )}

        <div className="grid grid-cols-2 gap-3 text-[12px]">
          <div>
            <span className="text-muted">重要性</span>
            <div className="mt-1">
              <div className="h-1.5 rounded-full bg-tertiary overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${fact.importance * 100}%`,
                    background: fact.importance >= 0.7 ? 'var(--color-success)' :
                      fact.importance >= 0.4 ? 'var(--color-warning)' : 'var(--color-text-secondary)',
                  }}
                />
              </div>
              <span className="mt-0.5">{Math.round(fact.importance * 100)}%</span>
            </div>
          </div>
          <div>
            <span className="text-muted">隐私等级</span>
            <p>{fact.privacy_level === 'public' ? '公开' : fact.privacy_level === 'sensitive' ? '敏感' : '私有'}</p>
          </div>
          <div>
            <span className="text-muted">创建时间</span>
            <p>{formatDate(fact.created_at)}</p>
          </div>
          <div>
            <span className="text-muted">最后活跃</span>
            <p>{formatDate(fact.last_accessed_at)}</p>
          </div>
        </div>

        {fact.tags && fact.tags.length > 0 && (
          <div className="flex gap-1.5">
            {fact.tags.map((tag) => (
              <Badge key={tag} variant="accent">{tag}</Badge>
            ))}
          </div>
        )}

        {fact.source_session_id && (
          <p className="text-[11px] text-muted">
            来源会话：{fact.source_session_id.slice(0, 8)}…
          </p>
        )}
      </div>
    </div>
  );
}
