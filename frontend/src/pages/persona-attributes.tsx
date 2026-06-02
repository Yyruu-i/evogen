import { useState, useEffect } from 'react';
import { Save, MessageSquare } from 'lucide-react';
import { usePersona, useUpdatePersona } from '@/hooks/use-persona';
import { personaApi } from '@/lib/api';
import { Skeleton } from '@/components/shared/skeleton';

export function PersonaAttributesPage() {
  const { data, isLoading } = usePersona();
  const updatePersona = useUpdatePersona();
  const [attrs, setAttrs] = useState<Record<string, unknown>>({});
  const [previewPrompt, setPreviewPrompt] = useState('');
  const [showPreview, setShowPreview] = useState(false);

  useEffect(() => {
    if (data?.attributes) {
      setAttrs({ ...data.attributes } as unknown as Record<string, unknown>);
    }
  }, [data]);

  const handleChange = (key: string, value: unknown) => {
    setAttrs((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => updatePersona.mutate(attrs);

  const handleShowPreview = async () => {
    try {
      const result = await personaApi.previewPrompt();
      setPreviewPrompt(result.prompt_injection);
      setShowPreview(true);
    } catch {
      setPreviewPrompt('（预览功能需要后端支持）');
      setShowPreview(true);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-lg space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="max-w-lg">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-[15px] font-semibold">属性编辑</h3>
          <p className="text-[12px] text-muted mt-0.5">配置你的 AI 人格参数</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary h-8 text-[12px]" onClick={handleShowPreview}>
            <MessageSquare style={{ width: 14, height: 14 }} />
            预览
          </button>
          <button className="btn-primary h-8 text-[12px]" onClick={handleSave} disabled={updatePersona.isPending}>
            <Save style={{ width: 14, height: 14 }} />
            保存
          </button>
        </div>
      </div>

      {showPreview && (
        <div className="glass-card p-4 mb-4">
          <h4 className="text-[12px] font-medium mb-2">System Prompt 预览</h4>
          <pre className="text-[12px] text-secondary whitespace-pre-wrap">{previewPrompt}</pre>
        </div>
      )}

      <div className="glass-card p-5 space-y-5">
        {/* Display name */}
        <div>
          <label className="text-[12px] font-medium text-secondary block mb-1.5">称呼</label>
          <input
            type="text"
            value={(attrs.display_name as string) || ''}
            onChange={(e) => handleChange('display_name', e.target.value)}
            placeholder="Agent 如何称呼你"
            className="w-full"
          />
        </div>

        {/* Sliders */}
        {[
          { key: 'conciseness', label: '简洁程度', desc: '0=详细解释, 1=极度简洁' },
          { key: 'formality', label: '正式程度', desc: '0=随意轻松, 1=正式严谨' },
          { key: 'warmth', label: '友好程度', desc: '0=冷漠疏离, 1=温暖亲切' },
          { key: 'directness', label: '直接程度', desc: '0=委婉含蓄, 1=直截了当' },
        ].map(({ key, label, desc }) => (
          <div key={key}>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[12px] font-medium text-secondary">{label}</label>
              <span className="text-[12px] font-mono text-accent">
                {Math.round(((attrs[key] as number) || 0.5) * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={(attrs[key] as number) || 0.5}
              onChange={(e) => handleChange(key, parseFloat(e.target.value))}
              className="w-full accent-indigo-500"
            />
            <p className="text-[11px] text-muted mt-0.5">{desc}</p>
          </div>
        ))}

        {/* Toggles */}
        <div className="space-y-3 pt-2 border-t border-color">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[12px] font-medium">自动批准安全工具</p>
              <p className="text-[11px] text-muted">让 Agent 自动执行确认安全的工具调用</p>
            </div>
            <button
              onClick={() => handleChange('auto_approve_tools', !attrs.auto_approve_tools)}
              className={`w-9 h-5 rounded-full transition-colors relative ${
                attrs.auto_approve_tools ? 'bg-accent' : 'bg-tertiary'
              }`}
            >
              <span className={`block w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${
                attrs.auto_approve_tools ? 'translate-x-5' : 'translate-x-0.5'
              }`} />
            </button>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[12px] font-medium">显示思考过程</p>
              <p className="text-[11px] text-muted">在对话中显示 Agent 的推理步骤</p>
            </div>
            <button
              onClick={() => handleChange('show_thinking', !attrs.show_thinking)}
              className={`w-9 h-5 rounded-full transition-colors relative ${
                attrs.show_thinking ? 'bg-accent' : 'bg-tertiary'
              }`}
            >
              <span className={`block w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${
                attrs.show_thinking ? 'translate-x-5' : 'translate-x-0.5'
              }`} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
