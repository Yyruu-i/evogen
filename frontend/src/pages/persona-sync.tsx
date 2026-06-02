import { Download, Upload, CheckCircle, AlertCircle } from 'lucide-react';
import { useState, useRef } from 'react';
import { personaApi } from '@/lib/api';

export function PersonaSyncPage() {
  const [message, setMessage] = useState('');
  const [msgType, setMsgType] = useState<'success' | 'error'>('success');
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage(text);
    setMsgType(type);
    setTimeout(() => setMessage(''), 4000);
  };

  const handleExport = async () => {
    try {
      const json = await personaApi.export();
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `evogen-persona-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showMsg('人格配置已导出');
    } catch (err) {
      showMsg(`导出失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error');
    }
  };

  const handleImport = async () => {
    fileRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text = await file.text();
      await personaApi.importPersona(text);
      showMsg('人格配置已导入，刷新页面查看更新');
      // Reload to reflect imported data
      setTimeout(() => window.location.reload(), 1500);
    } catch (err) {
      showMsg(`导入失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error');
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-1">同步状态</h3>
      <p className="text-[12px] text-muted mb-6">
        同一人格配置自动在所有平台（飞书、Telegram、CLI、Web）保持一致。
      </p>

      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center gap-3 p-3 rounded-lg bg-success/5 border border-success/10">
          <CheckCircle className="w-5 h-5 text-success flex-shrink-0" />
          <div>
            <p className="text-[13px] font-medium text-success">人格同步已启用</p>
            <p className="text-[11px] text-secondary">所有平台共享同一套人格配置。在一个平台上修改后，其他平台自动生效。</p>
          </div>
        </div>

        <div className="space-y-2 pt-3 border-t border-color">
          <h4 className="text-[13px] font-medium">备份与恢复</h4>
          <div className="flex gap-2">
            <button className="btn-secondary h-8 text-[12px]" onClick={handleExport}>
              <Download style={{ width: 14, height: 14 }} />
              导出配置
            </button>
            <button className="btn-secondary h-8 text-[12px]" onClick={handleImport} disabled={importing}>
              <Upload style={{ width: 14, height: 14 }} />
              {importing ? '导入中…' : '导入配置'}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>
          {message && (
            <p className={`text-[12px] flex items-center gap-1 ${
              msgType === 'success' ? 'text-success' : 'text-danger'
            }`}>
              {msgType === 'success'
                ? <CheckCircle style={{ width: 12, height: 12 }} />
                : <AlertCircle style={{ width: 12, height: 12 }} />
              }
              {message}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
