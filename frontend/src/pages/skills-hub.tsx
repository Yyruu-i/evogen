import { Globe, ArrowUpRight } from 'lucide-react';
import { EmptyState } from '@/components/shared/empty-state';

export function SkillsHubPage() {
  return (
    <div className="max-w-3xl">
      <h3 className="text-[15px] font-semibold mb-4">技能市场</h3>
      <EmptyState
        icon={Globe}
        title="即将推出"
        description="技能市场（EvoHub）将在 M1 阶段上线。届时你可以浏览、安装社区贡献的技能，也可以分享自己的技能。"
        action={{
          label: '了解技能市场',
          onClick: () => window.open('https://github.com/evogen', '_blank'),
        }}
      />
    </div>
  );
}
