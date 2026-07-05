import { useNavigate } from 'react-router-dom';
import { Shield, Code2, Server, BarChart, FileText, Sparkles } from 'lucide-react';

/* ── 专家定义 ────────────────────────────────────────── */
export interface ExpertDef {
  id: string;
  name: string;
  icon: typeof Shield;
  description: string;
  color: string;
  online: boolean;
}

const EXPERTS: ExpertDef[] = [
  { id: 'security-engineer', name: '安全工程师', icon: Shield, description: '渗透测试、漏洞扫描、安全评估', color: '#ff6b6b', online: true },
  { id: 'python-engineer', name: 'Python 工程师', icon: Code2, description: '代码编写、调试、重构、性能优化', color: '#4ecdc4', online: true },
  { id: 'ops-engineer', name: '运维工程师', icon: Server, description: '服务器部署、监控、故障排查', color: '#45b7d1', online: true },
  { id: 'data-analyst', name: '数据分析师', icon: BarChart, description: '数据清洗、可视化、统计建模', color: '#96ceb4', online: true },
  { id: 'doc-engineer', name: '文档工程师', icon: FileText, description: '技术文档、API文档、报告撰写', color: '#ffeaa7', online: true },
  { id: 'general-assistant', name: '通用助手', icon: Sparkles, description: '全能 Agent，什么都懂一点', color: '#a29bfe', online: true },
];

export { EXPERTS };

/* ── 在线统计 ────────────────────────────────────────── */
const onlineCount = EXPERTS.filter(e => e.online).length;
const totalCount = EXPERTS.length;

/* ── 卡片组件 ────────────────────────────────────────── */
function ExpertCard({ expert }: { expert: ExpertDef }) {
  const navigate = useNavigate();
  const Icon = expert.icon;
  return (
    <button
      className="glass-card group relative flex flex-col items-start gap-2.5 p-5 text-left transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
      style={{
        background: 'var(--color-bg-glass)',
        border: '1px solid var(--color-border-glass)',
      }}
      onClick={() => navigate(`/experts/${expert.id}/chat`)}
    >
      {/* Online indicator */}
      <div
        className="absolute top-3 right-3 flex items-center gap-1.5 text-[10px] font-medium"
        style={{ color: expert.online ? 'var(--color-mint)' : 'var(--color-text-muted)' }}
      >
        <span
          className={`inline-block w-2 h-2 rounded-full ${expert.online ? 'animate-pulse' : ''}`}
          style={{ background: expert.online ? 'var(--color-mint)' : 'var(--color-text-muted)' }}
        />
        {expert.online ? '在线' : '离线'}
      </div>

      {/* Icon */}
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200 group-hover:shadow-lg"
        style={{ background: `${expert.color}18` }}
      >
        <Icon className="w-5 h-5" style={{ color: expert.color }} />
      </div>

      {/* Name */}
      <p className="text-[14px] font-semibold text-primary">{expert.name}</p>

      {/* Description */}
      <p className="text-[12px] text-secondary leading-relaxed">{expert.description}</p>
    </button>
  );
}

/* ── 页面组件 ────────────────────────────────────────── */
export function ExpertListPage() {
  return (
    <div className="max-w-2xl">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-[18px] font-bold">专家</h2>
          <p className="text-[12px] text-muted mt-0.5">
            {onlineCount}/{totalCount} · {onlineCount === totalCount ? '全部在线' : `${onlineCount} 个在线`}
          </p>
        </div>
      </div>

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {EXPERTS.map((expert) => (
          <ExpertCard key={expert.id} expert={expert} />
        ))}
      </div>
    </div>
  );
}
