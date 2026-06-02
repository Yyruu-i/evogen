import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { useSearchMemory } from '@/hooks/use-memory';
import { LAYER_LABELS, FACT_TYPE_LABELS, formatDate, truncate } from '@/lib/utils';
import { Badge } from '@/components/shared/badge';
import { EmptyState } from '@/components/shared/empty-state';

export function MemorySearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const { data, isFetching } = useSearchMemory(query);
  const facts = data?.facts || [];

  return (
    <div className="max-w-3xl">
      <h3 className="text-[15px] font-semibold mb-4">记忆搜索</h3>

      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索记忆…（支持语义搜索）"
          className="w-full pl-10 pr-4 py-2.5 text-[13px] rounded-xl"
        />
      </div>

      {!query ? (
        <EmptyState icon={Search} title="输入关键词搜索" description="EvoGen 支持语义搜索，找到含义相近的记忆。" />
      ) : isFetching ? (
        <p className="text-[13px] text-muted text-center py-8">搜索中…</p>
      ) : facts.length === 0 ? (
        <EmptyState icon={Search} title="无匹配结果" description={`没有找到与「${query}」相关的记忆。`} />
      ) : (
        <div className="space-y-2">
          <p className="text-[12px] text-muted mb-2">找到 {facts.length} 条相关记忆</p>
          {facts.map((fact) => (
            <div
              key={fact.id}
              className="glass-card p-4 cursor-pointer group"
              onClick={() => navigate(`/memory/${fact.id}`)}
            >
              <p className="text-[13px] leading-relaxed">{truncate(fact.content, 150)}</p>
              <div className="flex items-center gap-2 mt-2">
                <Badge>{FACT_TYPE_LABELS[fact.type] || fact.type}</Badge>
                <span className="text-[11px] text-secondary">{LAYER_LABELS[fact.layer]}</span>
                <span className="text-[11px] text-muted">{formatDate(fact.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
