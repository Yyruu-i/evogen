import { useSkills } from '@/hooks/use-skills';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';
import { Wrench } from 'lucide-react';

export function SettingsSkillsPage() {
  const { data, isLoading } = useSkills();
  const skills = data?.skills || [];

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-4">技能设置</h3>

      {isLoading ? (
        <ListSkeleton rows={5} />
      ) : skills.length === 0 ? (
        <EmptyState icon={Wrench} title="暂无技能" description="安装技能扩展 Agent 的能力。" />
      ) : (
        <div className="space-y-2">
          {skills.map((skill) => (
            <div key={skill.id} className="glass-card p-3 flex items-center justify-between">
              <div>
                <p className="text-[13px] font-medium">{skill.name}</p>
                <p className="text-[11px] text-muted">v{skill.version} · 使用 {skill.use_count} 次</p>
              </div>
              <Badge variant={skill.source === 'local' ? 'default' : 'accent'}>
                {skill.source === 'local' ? '本地' : skill.source === 'hub' ? '市场' : '自动'}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
