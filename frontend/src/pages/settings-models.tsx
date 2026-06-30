import { useState, useEffect } from 'react';
import { Cpu, CheckCircle, Plus, Trash2, Key, Globe, X } from 'lucide-react';
import { systemApi } from '@/lib/api';
import { Skeleton } from '@/components/shared/skeleton';

const BUILTIN_MODELS = [
  { id: 'deepseek-chat', label: 'DeepSeek-V3 (Chat)', description: '通用对话模型，快速响应', provider: 'DeepSeek' },
  { id: 'deepseek-reasoner', label: 'DeepSeek-R1 (Reasoner)', description: '推理模型，有思考过程，适合复杂问题', provider: 'DeepSeek' },
  { id: 'deepseek-v4-pro', label: 'DeepSeek-V4 Pro', description: '增强版通用模型', provider: 'DeepSeek' },
];

interface CustomModel {
  label: string;
  base_url: string;
  description: string;
  api_key_masked?: string;
  api_key?: string;
}

export function SettingsModelsPage() {
  const [currentModel, setCurrentModel] = useState('deepseek-chat');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [customModels, setCustomModels] = useState<Record<string, CustomModel>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [formData, setFormData] = useState({ id: '', label: '', api_key: '', base_url: 'https://open.bigmodel.cn/api/paas/v4', description: '' });
  const [savingModel, setSavingModel] = useState(false);

  useEffect(() => {
    systemApi.getConfig()
      .then((config: any) => {
        if (config?.llm_model) {
          setCurrentModel(String(config.llm_model));
        }
      })
      .catch((err) => console.warn('Failed to load model config:', err))
      .finally(() => setLoading(false));

    loadCustomModels();
  }, []);

  const loadCustomModels = async () => {
    try {
      const models = await systemApi.getCustomModels();
      setCustomModels(models as Record<string, CustomModel>);
    } catch (err) {
      console.warn('Failed to load custom models:', err);
    }
  };

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

  const handleAddModel = async () => {
    if (!formData.id || !formData.api_key) return;
    setSavingModel(true);
    try {
      await systemApi.addCustomModel({
        id: formData.id,
        label: formData.label || formData.id,
        api_key: formData.api_key,
        base_url: formData.base_url,
        description: formData.description,
      });
      setShowAddForm(false);
      setFormData({ id: '', label: '', api_key: '', base_url: 'https://open.bigmodel.cn/api/paas/v4', description: '' });
      await loadCustomModels();
    } catch (err) {
      console.error('Failed to add model:', err);
    } finally {
      setSavingModel(false);
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    try {
      await systemApi.deleteCustomModel(modelId);
      await loadCustomModels();
      if (currentModel === modelId) {
        handleSelectModel('deepseek-chat');
      }
    } catch (err) {
      console.error('Failed to delete model:', err);
    }
  };

  const allModels = [
    ...BUILTIN_MODELS,
    ...Object.entries(customModels).map(([id, m]) => ({
      id,
      label: m.label || id,
      description: m.description || `自定义模型 · ${m.base_url}`,
      provider: '自定义',
      apiKeyMasked: m.api_key_masked,
      isCustom: true as const,
    })),
  ];

  const getModelLabel = (id: string) => {
    const found = allModels.find(m => m.id === id);
    return found?.label || id;
  };

  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-1">模型配置</h3>
      <p className="text-[12px] text-muted mb-6">
        选择要使用的 AI 模型。切换后新对话将使用所选模型。
        也可以添加自定义模型（需填入 API Key 和接口地址）。
      </p>

      {saved && (
        <div className="mb-4 px-4 py-2 rounded-lg text-[12px] font-medium flex items-center gap-2"
          style={{ background: 'rgba(0,255,136,0.1)', color: 'var(--color-mint)' }}>
          <CheckCircle className="w-4 h-4" />
          模型已切换，新对话将使用 <strong>{getModelLabel(currentModel)}</strong>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {allModels.map((model) => {
              const isActive = currentModel === model.id;
              const isCustom = 'isCustom' in model && model.isCustom;
              return (
                <button
                  key={model.id}
                  onClick={() => handleSelectModel(model.id)}
                  disabled={saving}
                  className="w-full text-left p-4 rounded-xl transition-all duration-200 hover:scale-[1.01] disabled:opacity-70 relative group"
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
                        {isCustom && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                            style={{ background: 'rgba(255,165,0,0.15)', color: 'orange' }}>
                            自定义
                          </span>
                        )}
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
                        {'apiKeyMasked' in model && model.apiKeyMasked && (
                          <> · API Key: {model.apiKeyMasked}</>
                        )}
                      </p>
                    </div>
                    {isActive && (
                      <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
                    )}
                    {isCustom && !isActive && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteModel(model.id); }}
                        className="w-6 h-6 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ background: 'rgba(255,0,0,0.1)', color: 'var(--color-danger)' }}
                        title="删除此模型"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* 添加自定义模型按钮 */}
          {!showAddForm && (
            <button
              onClick={() => setShowAddForm(true)}
              className="w-full mt-3 p-3 rounded-xl border border-dashed text-[13px] font-medium transition-all hover:scale-[1.01] flex items-center justify-center gap-2"
              style={{
                borderColor: 'var(--color-border-glass)',
                color: 'var(--color-accent)',
              }}
            >
              <Plus className="w-4 h-4" />
              添加自定义模型
            </button>
          )}

          {/* 添加模型表单 */}
          {showAddForm && (
            <div className="mt-3 p-4 rounded-xl border"
              style={{
                background: 'var(--glass-bg, rgba(255,255,255,0.04))',
                borderColor: 'var(--color-border-glass)',
              }}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[13px] font-semibold">新建自定义模型</span>
                <button onClick={() => setShowAddForm(false)} className="text-muted hover:text-primary">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-[11px] text-secondary block mb-1">模型 ID *</label>
                  <input
                    type="text"
                    value={formData.id}
                    onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                    placeholder="如 glm-5.1、kimi-2.6"
                    className="w-full text-[13px] px-3 py-2 rounded-lg"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-secondary block mb-1">显示名称</label>
                  <input
                    type="text"
                    value={formData.label}
                    onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                    placeholder="如 GLM-5.1、Kimi 2.6"
                    className="w-full text-[13px] px-3 py-2 rounded-lg"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-secondary block mb-1">
                    <Key className="w-3 h-3 inline mr-1" />
                    API Key *
                  </label>
                  <input
                    type="password"
                    value={formData.api_key}
                    onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                    placeholder="输入 API Key"
                    className="w-full text-[13px] px-3 py-2 rounded-lg"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-secondary block mb-1">
                    <Globe className="w-3 h-3 inline mr-1" />
                    Base URL
                  </label>
                  <input
                    type="text"
                    value={formData.base_url}
                    onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                    placeholder="如 https://open.bigmodel.cn/api/paas/v4"
                    className="w-full text-[13px] px-3 py-2 rounded-lg"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-secondary block mb-1">描述（可选）</label>
                  <input
                    type="text"
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="模型特点说明"
                    className="w-full text-[13px] px-3 py-2 rounded-lg"
                  />
                </div>
                <button
                  onClick={handleAddModel}
                  disabled={savingModel || !formData.id || !formData.api_key}
                  className="w-full px-4 py-2 text-[12px] font-medium rounded-lg transition-all disabled:opacity-50"
                  style={{
                    background: 'linear-gradient(135deg, var(--color-accent), var(--color-coral))',
                    color: '#fff',
                  }}
                >
                  {savingModel ? '保存中…' : '保存模型'}
                </button>
              </div>
            </div>
          )}

          {/* 常用模型参考 */}
          <div className="mt-3 glass-card-accent p-4">
            <p className="text-[11px] font-medium text-secondary mb-2">常用自定义模型参考地址</p>
            <div className="text-[11px] text-muted space-y-1">
              <p>• GLM-5.1 / GLM-4：<code className="text-accent text-[10px]">https://open.bigmodel.cn/api/paas/v4</code></p>
              <p>• Kimi 2.6：<code className="text-accent text-[10px]">https://api.moonshot.cn/v1</code></p>
              <p>• DeepSeek：<code className="text-accent text-[10px]">https://api.deepseek.com</code></p>
              <p>• OpenAI：<code className="text-accent text-[10px]">https://api.openai.com/v1</code></p>
            </div>
          </div>
        </>
      )}

      <div className="mt-6 glass-card-accent p-5 space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
          <p className="text-[12px] font-medium">关于模型切换</p>
        </div>
        <p className="text-[11px] text-muted leading-relaxed">
          切换模型后，新对话将使用所选模型。已存在的对话仍使用切换前的模型继续对话。
          <br />
          自定义模型的 API Key 和接口地址会持久化保存，重启后仍然有效。
        </p>
      </div>
    </div>
  );
}
