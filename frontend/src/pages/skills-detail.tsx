import { useParams, useNavigate } from 'react-router-dom';
import { useSkills } from '@/hooks/use-skills';
import { Badge } from '@/components/shared/badge';
import { Wrench, ArrowLeft, Zap, Activity, Tag } from 'lucide-react';
import { skillLabel, SKILL_NAME_CN, SKILL_CATEGORY_CN, SKILL_TAG_CN } from '@/lib/utils';

export function SkillsDetailPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const navigate = useNavigate();
  const { data, isLoading } = useSkills();
  const skill = data?.skills?.find((s) => s.id === skillId);

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto pt-8">
        <div className="space-y-3">
          <div className="skeleton h-6 w-48" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-2/3" />
        </div>
      </div>
    );
  }

  if (!skill) {
    return (
      <div className="max-w-3xl mx-auto pt-8 text-center">
        <Wrench className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--color-text-muted)' }} />
        <h3 className="text-[15px] font-semibold mb-2">技能未找到</h3>
        <p className="text-[13px] text-secondary mb-4">该技能可能已被删除或 ID 无效。</p>
        <button
          onClick={() => navigate('/skills/local')}
          className="px-4 py-2 text-[13px] rounded-lg font-medium text-primary"
          style={{ background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)' }}
        >
          返回技能列表
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Back button */}
      <button
        onClick={() => navigate('/skills/local')}
        className="flex items-center gap-1.5 text-[12px] text-secondary hover:text-primary mb-4 transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        返回技能列表
      </button>

      {/* Header */}
      <div className="glass-card-accent p-5 mb-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <h2 className="text-[18px] font-bold mb-1">{skillLabel(skill.name, SKILL_NAME_CN)}</h2>
            <p className="text-[13px] text-secondary leading-relaxed">{skillLabel(skill.description, SKILL_NAME_CN)}</p>
          </div>
          <Badge variant={skill.source === 'local' ? 'default' : 'accent'} className="ml-3">
            {skill.source === 'local' ? '本地' : skill.source === 'hub' ? '市场' : '自动生成'}
          </Badge>
        </div>

        {/* Meta grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
            <div>
              <p className="text-[10px] text-muted">使用次数</p>
              <p className="text-[13px] font-semibold">{skill.use_count}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Zap className="w-3.5 h-3.5" style={{ color: 'var(--color-mint)' }} />
            <div>
              <p className="text-[10px] text-muted">成功率</p>
              <p className="text-[13px] font-semibold" style={{ color: 'var(--color-mint)' }}>
                {Math.round(skill.success_rate * 100)}%
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Tag className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
            <div>
              <p className="text-[10px] text-muted">版本</p>
              <p className="text-[13px] font-semibold">v{skill.version}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Wrench className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
            <div>
              <p className="text-[10px] text-muted">分类</p>
              <p className="text-[13px] font-semibold">{skillLabel(skill.category, SKILL_CATEGORY_CN)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tags */}
      {skill.tags && skill.tags.length > 0 && (
        <div className="glass-card-accent p-4 mb-4">
          <h4 className="text-[12px] font-semibold mb-2">技能标签</h4>
          <div className="flex flex-wrap gap-1.5">
            {skill.tags.map((tag) => (
              <Badge key={tag} variant="info">{skillLabel(tag, SKILL_TAG_CN)}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Metadata */}
      <div className="glass-card-accent p-4">
        <h4 className="text-[12px] font-semibold mb-2">元信息</h4>
        <div className="space-y-1.5">
          <div className="flex justify-between text-[12px]">
            <span className="text-muted">ID</span>
            <span className="font-mono text-[11px] text-secondary">{skill.id}</span>
          </div>
          <div className="flex justify-between text-[12px]">
            <span className="text-muted">创建时间</span>
            <span className="text-secondary">{skill.created_at}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
