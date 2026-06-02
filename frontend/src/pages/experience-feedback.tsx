import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle, XCircle, ChevronRight } from 'lucide-react';
import { useFeedback, useUpdateFeedbackStatus } from '@/hooks/use-experience';
import { formatDate, FEEDBACK_RATING_LABELS, FEEDBACK_STATUS_LABELS } from '@/lib/utils';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';

export function FeedbackQueuePage() {
  const [statusFilter, setStatusFilter] = useState('pending');
  const { data, isLoading } = useFeedback({ status: statusFilter, limit: 50 });
  const updateStatus = useUpdateFeedbackStatus();
  const navigate = useNavigate();

  const feedback = data?.feedback || [];
  const total = data?.total || 0;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-[15px] font-semibold">待反馈队列</h3>
          <p className="text-[12px] text-muted mt-0.5">{total} 条反馈</p>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        {['pending', 'reviewed', 'applied', 'dismissed'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 text-[12px] rounded-md font-medium transition-colors ${
              statusFilter === s ? 'bg-accent/20 text-accent' : 'bg-tertiary text-secondary hover:text-primary'
            }`}
          >
            {FEEDBACK_STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {isLoading ? (
        <ListSkeleton rows={5} />
      ) : feedback.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title="暂无待处理反馈"
          description="所有反馈已处理完毕。Agent 会继续积累经验。"
        />
      ) : (
        <div className="space-y-2">
          {feedback.map((fb) => (
            <div key={fb.id} className="glass-card p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant={fb.rating === 'good' ? 'success' : fb.rating === 'bad' ? 'danger' : 'warning'}>
                  {FEEDBACK_RATING_LABELS[fb.rating]}
                </Badge>
                <Badge>{FEEDBACK_STATUS_LABELS[fb.status]}</Badge>
                <span className="text-[11px] text-muted">{formatDate(fb.created_at)}</span>
              </div>
              {fb.note && <p className="text-[13px]">{fb.note}</p>}
              <div className="flex items-center justify-between">
                <button
                  className="text-[12px] text-accent hover:underline"
                  onClick={() => navigate(`/experience/${fb.trajectory_id}`)}
                >
                  查看轨迹 <ChevronRight className="w-3 h-3 inline" />
                </button>
                {fb.status === 'pending' && (
                  <div className="flex gap-1.5">
                    <button
                      className="btn-primary h-6 text-[11px] px-3"
                      onClick={() => updateStatus.mutate({ id: fb.id, status: 'applied' })}
                    >
                      <CheckCircle style={{ width: 12, height: 12 }} />
                      应用
                    </button>
                    <button
                      className="btn-ghost h-6 text-[11px] px-3"
                      onClick={() => updateStatus.mutate({ id: fb.id, status: 'dismissed' })}
                    >
                      <XCircle style={{ width: 12, height: 12 }} />
                      忽略
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
