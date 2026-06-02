import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Plus, ChevronRight, Trash2 } from 'lucide-react';
import { useMemory, useCreateMemory, useDeleteMemory } from '@/hooks/use-memory';
import { LAYER_LABELS, FACT_TYPE_LABELS, formatDate, truncate } from '@/lib/utils';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';
import type { MemoryLayer, MemoryFactType, ManualFactInput } from '@/types';

const LAYERS: { value: string; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'working', label: '工作' },
  { value: 'core', label: '核心' },
  { value: 'transient', label: '瞬态' },
  { value: 'archive', label: '归档' },
];

const TYPES: { value: string; label: string }[] = [
  { value: '', label: '全部类型' },
  { value: 'preference', label: '偏好' },
  { value: 'fact', label: '事实' },
  { value: 'procedure', label: '流程' },
  { value: 'relationship', label: '关系' },
];

export function MemoryListPage() {
  const navigate = useNavigate();
  const [layer, setLayer] = useState('all');
  const [type, setType] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newType, setNewType] = useState<MemoryFactType>('fact');

  const { data, isLoading } = useMemory({
    layer: layer === 'all' ? undefined : layer,
    type: type || undefined,
    limit: 50,
  });
  const createMemory = useCreateMemory();
  const deleteMemory = useDeleteMemory();

  const facts = data?.facts || [];
  const total = data?.total || 0;

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    const input: ManualFactInput = { content: newContent.trim(), type: newType };
    await createMemory.mutateAsync(input);
    setNewContent('');
    setShowAdd(false);
  };

  const importanceColor = (v: number) => {
    if (v >= 0.7) return 'text-success';
    if (v >= 0.4) return 'text-warning';
    return 'text-secondary';
  };

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-[15px] font-semibold">记忆列表</h3>
          <p className="text-[12px] text-muted mt-0.5">{total} 条记忆</p>
        </div>
        <button className="btn-primary h-8 text-[12px]" onClick={() => setShowAdd(true)}>
          <Plus style={{ width: 14, height: 14 }} />
          添加记忆
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <div className="flex rounded-lg bg-tertiary p-0.5">
          {LAYERS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setLayer(value)}
              className={`px-3 py-1 text-[12px] rounded-md font-medium transition-colors ${
                layer === value ? 'bg-primary text-primary shadow-sm' : 'text-secondary hover:text-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="px-3 py-1 text-[12px] rounded-lg"
        >
          {TYPES.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="glass-card p-4 mb-4 space-y-3">
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="输入记忆内容，例如：我喝咖啡不加糖"
            rows={2}
            className="w-full"
          />
          <div className="flex items-center gap-2">
            <select
              value={newType}
              onChange={(e) => setNewType(e.target.value as MemoryFactType)}
              className="px-3 py-1 text-[12px] rounded-lg"
            >
              <option value="fact">事实</option>
              <option value="preference">偏好</option>
              <option value="procedure">流程</option>
              <option value="relationship">关系</option>
            </select>
            <button className="btn-primary h-7 text-[12px] px-3" onClick={handleAdd} disabled={createMemory.isPending}>
              保存
            </button>
            <button className="btn-ghost h-7 text-[12px]" onClick={() => setShowAdd(false)}>取消</button>
          </div>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <ListSkeleton rows={6} />
      ) : facts.length === 0 ? (
        <EmptyState
          icon={Search}
          title="暂无记忆"
          description="Agent 会在对话中自动记住关于你的信息，你也可以手动添加。"
          action={{ label: '手动添加', onClick: () => setShowAdd(true) }}
        />
      ) : (
        <div className="space-y-2">
          {facts.map((fact) => (
            <div
              key={fact.id}
              className="glass-card-accent p-4 flex items-start gap-3 cursor-pointer group"
              onClick={() => navigate(`/memory/${fact.id}`)}
            >
              <div className="flex-1 min-w-0">
                <p className="text-[13px] leading-relaxed">{truncate(fact.content, 120)}</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant={
                    fact.type === 'preference' ? 'info' :
                    fact.type === 'procedure' ? 'accent' :
                    fact.type === 'relationship' ? 'warning' : 'default'
                  }>
                    {FACT_TYPE_LABELS[fact.type] || fact.type}
                  </Badge>
                  <span className="text-[11px] text-secondary">{LAYER_LABELS[fact.layer]}</span>
                  <span className={`text-[11px] ${importanceColor(fact.importance)}`}>
                    重要性 {Math.round(fact.importance * 100)}%
                  </span>
                  <span className="text-[11px] text-muted">{formatDate(fact.created_at)}</span>
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  className="p-1 rounded hover:bg-hover text-muted hover:text-danger"
                  onClick={(e) => { e.stopPropagation(); deleteMemory.mutate(fact.id); }}
                >
                  <Trash2 style={{ width: 14, height: 14 }} />
                </button>
                <ChevronRight className="w-4 h-4 text-muted" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
