import { useState, useEffect } from 'react';
import { FileText, Eye, EyeOff, Loader2, AlertCircle } from 'lucide-react';

interface TemplateSection {
  label: string;
  required: boolean;
  fields: string[];
}

interface Template {
  id: string;
  name: string;
  description: string;
  version: string;
  section_count: number;
  sections: TemplateSection[];
}

export function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/report/templates')
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) setTemplates(d.data);
        else setError('加载模板失败');
      })
      .catch(() => setError('网络错误'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--color-text-muted)' }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertCircle className="w-8 h-8 mx-auto mb-2" style={{ color: 'var(--color-danger)' }} />
          <p style={{ color: 'var(--color-text-muted)' }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <FileText className="w-6 h-6" style={{ color: 'var(--color-accent)' }} />
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>模板库</h1>
      </div>

      <p className="mb-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
        选择模板生成结构化报告，报告将存入当前对话的制品面板。
      </p>

      <div className="space-y-4">
        {templates.map((t) => {
          const isExpanded = expandedId === t.id;
          return (
            <div
              key={t.id}
              className="rounded-xl border overflow-hidden transition-all duration-200"
              style={{
                borderColor: 'var(--color-border-glass)',
                background: 'var(--color-bg-glass)',
              }}
            >
              {/* Card header */}
              <button
                onClick={() => setExpandedId(isExpanded ? null : t.id)}
                className="w-full flex items-center justify-between p-4 hover:bg-[var(--color-bg-hover)] transition-colors"
              >
                <div className="flex items-center gap-3 text-left">
                  <FileText className="w-5 h-5 shrink-0" style={{ color: 'var(--color-accent)' }} />
                  <div>
                    <div className="font-medium text-sm" style={{ color: 'var(--color-text-primary)' }}>
                      {t.name}
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                      {t.id} · v{t.version} · {t.section_count} 个章节
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {isExpanded ? (
                    <EyeOff className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
                  ) : (
                    <Eye className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
                  )}
                </div>
              </button>

              {/* Expanded content */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3 border-t" style={{ borderColor: 'var(--color-border-glass)' }}>
                  <p className="text-sm pt-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {t.description || '暂无描述'}
                  </p>

                  {/* 模板结构展示 */}
                  {t.sections && t.sections.length > 0 && (
                    <div className="space-y-2">
                      {t.sections.map((sec, i) => (
                        <div
                          key={i}
                          className="rounded-lg p-3 text-sm"
                          style={{
                            background: 'rgba(0,0,0,0.03)',
                            border: '1px solid var(--color-border-glass)',
                          }}
                        >
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
                              {sec.label}
                            </span>
                            {sec.required && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded" style={{
                                background: 'rgba(255,107,107,0.1)',
                                color: 'var(--color-accent)',
                              }}>
                                必填
                              </span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {sec.fields.map((f, j) => (
                              <span
                                key={j}
                                className="text-xs px-2 py-0.5 rounded-full"
                                style={{
                                  background: 'rgba(100,100,200,0.08)',
                                  color: 'var(--color-text-secondary)',
                                  border: '1px solid rgba(100,100,200,0.12)',
                                }}
                              >
                                {f}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
