import { Radio, CheckCircle, XCircle, Plus } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { systemApi } from '@/lib/api';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { useState } from 'react';

export function SettingsPlatformsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['system', 'platforms'],
    queryFn: () => systemApi.platforms(),
    staleTime: 30000,
  });
  const [showAdd, setShowAdd] = useState(false);
  const [newToken, setNewToken] = useState('');
  const [newPlatform, setNewPlatform] = useState('telegram');

  const platforms = data?.platforms || [];

  const handleConnect = async () => {
    try {
      await systemApi.connectPlatform(newPlatform, newToken);
      setShowAdd(false);
      setNewToken('');
    } catch {
      // ignore
    }
  };

  return (
    <div className="max-w-lg">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-[15px] font-semibold">平台管理</h3>
          <p className="text-[12px] text-muted mt-0.5">管理已连接的消息平台</p>
        </div>
        <button className="btn-primary h-8 text-[12px]" onClick={() => setShowAdd(true)}>
          <Plus style={{ width: 14, height: 14 }} />
          添加通道
        </button>
      </div>

      {showAdd && (
        <div className="glass-card p-4 mb-4 space-y-3">
          <select
            value={newPlatform}
            onChange={(e) => setNewPlatform(e.target.value)}
            className="w-full"
          >
            <option value="telegram">Telegram</option>
            <option value="discord">Discord</option>
          </select>
          <input
            type="text"
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
            placeholder="Bot Token"
            className="w-full"
          />
          <div className="flex gap-2">
            <button className="btn-primary h-7 text-[12px]" onClick={handleConnect}>连接</button>
            <button className="btn-ghost h-7 text-[12px]" onClick={() => setShowAdd(false)}>取消</button>
          </div>
        </div>
      )}

      {isLoading ? (
        <ListSkeleton rows={3} />
      ) : platforms.length === 0 ? (
        <p className="text-[13px] text-muted text-center py-12">暂无已连接平台。点击「添加通道」开始。</p>
      ) : (
        <div className="space-y-2">
          {platforms.map((p) => (
            <div key={p.name} className="glass-card p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Radio className="w-5 h-5 text-accent" />
                <div>
                  <p className="text-[13px] font-medium capitalize">{p.name}</p>
                  <p className="text-[11px] text-muted">已连接@{p.connected_at ? new Date(p.connected_at).toLocaleString() : '-'}</p>
                </div>
              </div>
              <Badge variant={p.status === 'connected' ? 'success' : 'danger'}>
                {p.status === 'connected' ? (
                  <><CheckCircle style={{ width: 10, height: 10 }} /> 已连接</>
                ) : (
                  <><XCircle style={{ width: 10, height: 10 }} /> 断开</>
                )}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
