import { Cpu, CheckCircle } from 'lucide-react';

export function SettingsModelsPage() {
  return (
    <div className="max-w-lg">
      <h3 className="text-[15px] font-semibold mb-1">模型配置</h3>
      <p className="text-[12px] text-muted mb-6">
        EvoGen 支持多种 LLM 提供商。模型配置在 config.yaml 中管理。
      </p>

      <div className="glass-card-accent p-5 space-y-4">
        <div className="flex items-center gap-3 p-3 rounded-lg bg-success/5 border border-success/10">
          <CheckCircle className="w-5 h-5 text-success flex-shrink-0" />
          <div>
            <p className="text-[13px] font-medium text-success">Provider Pool 已激活</p>
            <p className="text-[11px] text-secondary">EvoGen 继承 Hermes 的多提供商路由，支持 100+ LLM 提供商。</p>
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-[12px] font-medium text-secondary block mb-1">默认模型</label>
            <input type="text" defaultValue="deepseek-v4-pro" className="w-full" readOnly />
            <p className="text-[11px] text-muted mt-0.5">在 config.yaml 的 model.default 中配置</p>
          </div>
          <div>
            <label className="text-[12px] font-medium text-secondary block mb-1">API Endpoint</label>
            <input type="text" defaultValue="https://api.deepseek.com" className="w-full" readOnly />
          </div>
        </div>

        <p className="text-[11px] text-muted">
          更详细的模型配置请使用 CLI：<code className="text-accent">evogen model</code> 或编辑 <code className="text-accent">~/.evogen/config.yaml</code>
        </p>
      </div>
    </div>
  );
}
