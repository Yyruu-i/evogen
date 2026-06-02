import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, MessageSquare, ThumbsUp, ThumbsDown, Minus } from 'lucide-react';
import { useTrajectory, useAddFeedback, useUpdateFeedbackStatus } from '@/hooks/use-experience';
import { formatDate, formatTime, FEEDBACK_RATING_LABELS, FEEDBACK_STATUS_LABELS } from '@/lib/utils';
import { Badge } from '@/components/shared/badge';
import { Skeleton } from '@/components/shared/skeleton';
import { useState } from 'react';

export function ExperienceDetailPage() {
  const { expId } = useParams<{ expId: string }>();
  const navigate = useNavigate();
  const { data: t, isLoading } = useTrajectory(expId || '');
  const addFeedback = useAddFeedback();
  const updateStatus = useUpdateFeedbackStatus();
  const [showFeedback, setShowFeedback] = useState(false);
  const [rating, setRating] = useState<'good' | 'neutral' | 'bad'>('good');
  const [note, setNote] = useState('');

  if (isLoading) {
    return (
      <div className="max-w-2xl space-y-4 p-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!t) return <p className="text-muted p-4">经验记录不存在。</p>;

  const handleSubmitFeedback = async () => {
    await addFeedback.mutateAsync({ trajectory_id: t.id, rating, note: note || undefined });
    setShowFeedback(false);
    setNote('');
  };

  return (
    <div className="max-w-2xl">
      <button className="btn-ghost mb-4 h-7 text-[12px]" onClick={() => navigate('/experience/list')}>
        <ArrowLeft style={{ width: 14, height: 14 }} />
        返回
      </button>

      <div className="glass-card p-6 space-y-4">
        <div className="flex items-center gap-2">
          {t.success ? (
            <CheckCircle className="w-5 h-5 text-success" />
          ) : (
            <XCircle className="w-5 h-5 text-danger" />
          )}
          <h3 className="text-[15px] font-semibold">{t.session_title || '未命名任务'}</h3>
        </div>

        <div className="flex gap-3 text-[12px] text-secondary">
          <span>{t.turn_count} 轮交互</span>
          <span>总 Token：{t.outcome?.total_tokens || '-'}</span>
          <span>耗时：{t.outcome?.wall_time_ms ? `${(t.outcome.wall_time_ms / 1000).toFixed(1)}s` : '-'}</span>
          <span>{formatDate(t.created_at)}</span>
        </div>

        {/* Turns timeline */}
        {t.turns && t.turns.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-[13px] font-medium">执行轨迹</h4>
            <div className="space-y-1">
              {t.turns.map((turn, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 px-3 rounded-lg bg-tertiary/50 text-[12px]">
                  <span className="text-muted w-6">#{turn.turn_index}</span>
                  <span className="text-secondary flex-1">
                    {turn.tool_calls?.map((tc) => `${tc.tool_name}`).join(', ') || 'LLM 响应'}
                  </span>
                  <span className="text-muted">{turn.token_usage} tokens</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Feedback section */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-[13px] font-medium">用户反馈</h4>
            <button className="btn-ghost h-7 text-[12px]" onClick={() => setShowFeedback(!showFeedback)}>
              <MessageSquare style={{ width: 14, height: 14 }} />
              添加反馈
            </button>
          </div>

          {showFeedback && (
            <div className="glass-card p-3 mb-3 space-y-3">
              <div className="flex gap-2">
                {(['good', 'neutral', 'bad'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRating(r)}
                    className={`px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors ${
                      rating === r ? 'bg-accent/20 text-accent' : 'bg-tertiary text-secondary'
                    }`}
                  >
                    {r === 'good' ? <ThumbsUp className="w-3.5 h-3.5 inline mr-1" /> :
                     r === 'bad' ? <ThumbsDown className="w-3.5 h-3.5 inline mr-1" /> :
                     <Minus className="w-3.5 h-3.5 inline mr-1" />}
                    {FEEDBACK_RATING_LABELS[r]}
                  </button>
                ))}
              </div>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="备注：例如「下次应该先确认再操作」"
                rows={2}
                className="w-full"
              />
              <div className="flex gap-2">
                <button className="btn-primary h-7 text-[12px]" onClick={handleSubmitFeedback} disabled={addFeedback.isPending}>
                  提交
                </button>
                <button className="btn-ghost h-7 text-[12px]" onClick={() => setShowFeedback(false)}>取消</button>
              </div>
            </div>
          )}

          {t.feedback && t.feedback.length > 0 ? (
            <div className="space-y-2">
              {t.feedback.map((fb) => (
                <div key={fb.id} className="bg-tertiary/50 rounded-lg p-3 text-[12px]">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant={fb.rating === 'good' ? 'success' : fb.rating === 'bad' ? 'danger' : 'warning'}>
                      {FEEDBACK_RATING_LABELS[fb.rating]}
                    </Badge>
                    <Badge>{FEEDBACK_STATUS_LABELS[fb.status]}</Badge>
                    <span className="text-muted">{formatDate(fb.created_at)}</span>
                  </div>
                  {fb.note && <p className="text-secondary mb-1.5">{fb.note}</p>}
                  {fb.status === 'pending' && (
                    <div className="flex gap-1.5 mt-1.5 pt-1.5 border-t border-color/30">
                      <button
                        className="px-2 py-0.5 rounded text-[10px] font-medium bg-success/10 text-success hover:bg-success/20 transition-colors"
                        onClick={() => updateStatus.mutate({ id: fb.id, status: 'reviewed' })}
                      >
                        已查看
                      </button>
                      <button
                        className="px-2 py-0.5 rounded text-[10px] font-medium bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
                        onClick={() => updateStatus.mutate({ id: fb.id, status: 'applied' })}
                      >
                        已应用
                      </button>
                      <button
                        className="px-2 py-0.5 rounded text-[10px] font-medium bg-muted/10 text-muted hover:bg-muted/20 transition-colors"
                        onClick={() => updateStatus.mutate({ id: fb.id, status: 'dismissed' })}
                      >
                        忽略
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[12px] text-muted">暂无反馈</p>
          )}
        </div>
      </div>
    </div>
  );
}
