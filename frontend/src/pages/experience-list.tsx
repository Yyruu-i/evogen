import { useNavigate } from 'react-router-dom';
import { CheckCircle, XCircle, Clock, ChevronRight, Download } from 'lucide-react';
import { useTrajectories } from '@/hooks/use-experience';
import { formatDate } from '@/lib/utils';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';

export function ExperienceListPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useTrajectories({ limit: 50 });
  const trajectories = data?.trajectories || [];

  const handleExportAll = () => {
    const blob = new Blob([JSON.stringify(trajectories, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `experience-export-${trajectories.length}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-[15px] font-semibold">对话摘要</h3>
          <p className="text-[12px] text-muted mt-0.5">Agent 的任务执行轨迹和经验积累</p>
        </div>
        <button
          className="btn-ghost h-7 text-[12px]"
          onClick={handleExportAll}
          disabled={trajectories.length === 0}
        >
          <Download className="w-3.5 h-3.5" />
          导出 JSON
        </button>
      </div>

      {isLoading ? (
        <ListSkeleton rows={6} />
      ) : trajectories.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="暂无经验记录"
          description="Agent 在完成任务后会自动记录经验轨迹。开始使用 EvoGen 后这里会逐渐丰富。"
        />
      ) : (
        <div className="space-y-2">
          {trajectories.map((t) => (
            <div
              key={t.id}
              className="glass-card-accent p-4 flex items-center gap-3 cursor-pointer group"
              onClick={() => navigate(`/experience/${t.id}`)}
            >
              {t.success ? (
                <CheckCircle className="w-5 h-5 text-success flex-shrink-0" />
              ) : (
                <XCircle className="w-5 h-5 text-danger flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium truncate">
                  {t.session_title || '未命名任务'}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[11px] text-muted">{t.turn_count} 轮</span>
                  <span className="text-[11px] text-muted">{formatDate(t.created_at)}</span>
                  {t.feedback_count > 0 && (
                    <Badge variant="info">{t.feedback_count} 条反馈</Badge>
                  )}
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
