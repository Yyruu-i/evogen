import { useState, useEffect } from 'react';
import { Cpu, CheckCircle, RefreshCw } from 'lucide-react';
import { systemApi } from '@/lib/api';
import { Skeleton } from '@/components/shared/skeleton';

const AVAILABLE_MODELS = [
  { id: 'deepseek-chat', label: 'DeepSeek-V3 (Chat)', description: '通用对话模型，快速响应', provider: 'DeepSeek' },
  { id: 'deepseek-reasoner', label: 'DeepSeek-R1 (Reasoner)', description: '推理模型，有思考过程，适合复杂问题', provider: 'DeepSeek' },
  { id: 'deepseek-v4-pro', label: 'DeepSeek-V4 Pro', description: '增强版通用模型', provider: 'DeepSeek' },
];

export function SettingsModelsPage() {
  const [currentModel, setCurrentModel] = useState('deepseek-chat');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    systemApi.getConfig()
      .then((config: any) => {
        if (config?.llm_model) {
          setCurrentModel(String(config.llm_model));
        }
      })
      .catch((err) => console.warn('Failed to load model config:', err))
      .finally(() => setLoading(false));
  }, []);

  const handleSelectModel = async (modelId: string) => {
    setCurrentModel(modelId);
    setSaving(true);
    setSaved(false);
    try {
      await systemApi.updateConfig({ llm_model: modelId });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      console.error('Failed to update model:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-1">模型配置</h3>
      <p className="text-[12px] text-muted mb-6">
        选择要使用的 AI 模型。切换后新对话将使用所选模型。
      </p>

      {saved && (
        <div className="mb-4 px-4 py-2 rounded-lg text-[12px] font-medium flex items-center gap-2"
          style={{ background: 'rgba(0,255,136,0.1)', color: 'var(--color-mint)' }}>
          <CheckCircle className="w-4 h-4" />
          模型已切换，新对话将使用 <strong>{AVAILABLE_MODELS.find(m => m.id === currentModel)?.label || currentModel}</strong>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {AVAILABLE_MODELS.map((model) => {
            const isActive = currentModel === model.id;
            return (
              <button
                key={model.id}
                onClick={() => handleSelectModel(model.id)}
                disabled={saving}
                className="w-full text-left p-4 rounded-xl transition-all duration-200 hover:scale-[1.01] disabled:opacity-70"
                style={{
                  background: isActive
                    ? 'linear-gradient(135deg, rgba(101,67,255,0.12), rgba(255,107,107,0.08))'
                    : 'var(--glass-bg, rgba(255,255,255,0.04))',
                  border: `1px solid ${isActive ? 'rgba(101,67,255,0.3)' : 'var(--color-border-glass, rgba(255,255,255,0.08))'}`,
                }}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    isActive ? 'bg-accent/20' : 'bg-tertiary/50'
                  }`}>
                    <Cpu className="w-5 h-5" style={{
                      color: isActive ? 'var(--color-accent)' : 'var(--color-text-muted)',
                    }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-semibold">{model.label}</span>
                      {isActive && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                          style={{ background: 'rgba(101,67,255,0.15)', color: 'var(--color-accent)' }}>
                          当前
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] text-muted mt-0.5">{model.description}</p>
                    <p className="text-[11px] text-secondary mt-0.5">
                      提供商: {model.provider} · ID: {model.id}
                    </p>
                  </div>
                  {isActive && (
                    <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-6 glass-card-accent p-5 space-y-3">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
          <p className="text-[12px] font-medium">关于模型切换</p>
        </div>
        <p className="text-[11px] text-muted leading-relaxed">
          切换模型后，新对话将使用所选模型。已存在的对话仍使用切换前的模型继续对话。
          <br />
          如果需要更改 Provider Pool 的默认配置，请编辑 <code className="text-accent">~/.evogen/config.yaml</code>。
        </p>
      </div>
    </div>
  );
}
