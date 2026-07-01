import { useState, useEffect } from 'react';
import { Highlight, themes } from 'prism-react-renderer';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Code2, Image, FileText, PanelRightClose, PanelRightOpen, X, ChevronDown, Download, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { artifactsApi } from '@/lib/api';
import { useChatContext } from '@/context/chat-context';
import type { Artifact as ArtifactType, ArtifactListResponse } from '@/types';

type ArtifactTab = 'code' | 'image' | 'doc';

const tabConfig: { id: ArtifactTab; label: string; icon: typeof Code2 }[] = [
  { id: 'code', label: '代码', icon: Code2 },
  { id: 'image', label: '图像', icon: Image },
  { id: 'doc', label: '文档', icon: FileText },
];

/** Export artifact content to Word document via backend */
async function exportToWord(artifact: ArtifactType): Promise<void> {
  try {
    const token = (() => { try { return localStorage.getItem('evogen-auth-token') || ''; } catch { return ''; } })();
    const res = await fetch('/api/v1/resource/export-docx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        content: artifact.content || '',
        title: artifact.title || 'EvoGen 文档',
      }),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => 'unknown');
      throw new Error(`HTTP ${res.status}: ${errText.slice(0, 100)}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title || 'export'}.docx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error('Word export failed:', err);
    alert(`导出 Word 失败: ${err instanceof Error ? err.message : '请重试'}`);
  }
}

export function ArtifactPanel() {
  const [isOpen, setIsOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<ArtifactTab>('code');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [imgErrors, setImgErrors] = useState<Set<string>>(new Set());
  const [savingToKnowledge, setSavingToKnowledge] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { state: { activeSessionId } } = useChatContext();

  // Track dark/light mode for code theme selection
  const [isDark, setIsDark] = useState(
    () => document.documentElement.classList.contains('dark'),
  );
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  const { data, isLoading } = useQuery<ArtifactListResponse>({
    queryKey: ['artifacts', { type: activeTab, session_id: activeSessionId }],
    queryFn: () => artifactsApi.list({ type: activeTab, session_id: activeSessionId }),
    staleTime: 10000,
    enabled: !!activeSessionId,
  });
  const rawArtifacts: ArtifactType[] = data?.artifacts || [];
  // Dedup by title — keep first occurrence
  const seen = new Set<string>();
  const artifacts = rawArtifacts.filter((a) => {
    if (seen.has(a.title)) return false;
    seen.add(a.title);
    return true;
  });

  const languageMap: Record<string, string> = {
    python: 'python',
    py: 'python',
    typescript: 'typescript',
    ts: 'typescript',
    javascript: 'javascript',
    js: 'javascript',
    json: 'json',
    html: 'html',
    css: 'css',
    markdown: 'markdown',
    md: 'markdown',
    yaml: 'yaml',
    yml: 'yaml',
    bash: 'bash',
    sh: 'bash',
    sql: 'sql',
    rust: 'rust',
    go: 'go',
    java: 'java',
  };

  const getHighlightLang = (artifact: ArtifactType): string => {
    if (artifact.language && languageMap[artifact.language]) {
      return languageMap[artifact.language];
    }
    const ext = artifact.title.split('.').pop()?.toLowerCase();
    return ext && languageMap[ext] ? languageMap[ext] : 'text';
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await artifactsApi.delete(id);
      queryClient.invalidateQueries({ queryKey: ['artifacts'] });
    } catch (err) {
      console.error('Failed to delete artifact:', err);
    }
  };

  const handleSaveToKnowledge = async (e: React.MouseEvent, artifact: ArtifactType) => {
    e.stopPropagation();
    setSavingToKnowledge(artifact.id);
    try {
      const res = await artifactsApi.toKnowledge(artifact.id);
      if (res?.knowledge_id) {
        alert(`✅ 已存入知识库\n来源: ${res.source}`);
      }
    } catch (err) {
      console.error('Failed to save to knowledge:', err);
      alert('❌ 存入知识库失败');
    } finally {
      setSavingToKnowledge(null);
    }
  };

  return (
    <>
      {/* Toggle button when panel is closed */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-30 w-8 h-20 rounded-l-xl flex items-center justify-center transition-all hover:w-10"
          style={{
            background: 'var(--color-bg-glass)',
            backdropFilter: 'blur(20px)',
            border: '1px solid var(--color-border-glass)',
            borderRight: 'none',
          }}
        >
          <PanelRightOpen className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
        </button>
      )}

      {/* ── Artifact Panel ────────────────────────────────────── */}
      <aside
        aria-hidden={!isOpen}
        className={cn(
          'h-full shrink-0 flex flex-col overflow-hidden relative z-20 transition-all duration-400',
          isOpen ? 'opacity-100' : 'opacity-0 w-0 overflow-hidden',
        )}
        style={{
          width: isOpen ? 'var(--artifact-width)' : '0px',
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderLeft: '1px solid var(--color-border-glass)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between shrink-0 h-12 px-4" style={{ borderBottom: '1px solid var(--color-border-glass)' }}>
          <span className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
            制品
          </span>
          <button
            onClick={() => setIsOpen(false)}
            className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-hover transition-colors"
          >
            <PanelRightClose className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 p-2 shrink-0">
          {tabConfig.map((tab) => {
            const Icon = tab.icon;
            const isActive = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setExpandedId(null); }}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all',
                  isActive ? '' : 'hover:text-primary',
                )}
                style={{
                  color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                  background: isActive ? 'rgba(255,107,107,0.1)' : 'transparent',
                }}
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Artifact list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {isLoading ? (
            <div className="space-y-3 p-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-24 w-full rounded-lg" />
              ))}
            </div>
          ) : artifacts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <FileText className="w-8 h-8" style={{ color: 'var(--color-text-muted)' }} />
              <span className="text-[12px]" style={{ color: 'var(--color-text-muted)' }}>
                暂无制品
              </span>
              <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                对话中生成的制品将在这里显示
              </span>
            </div>
          ) : (
            artifacts.map((artifact) => {
              const isExpanded = expandedId === artifact.id;
              const lang = activeTab === 'code' ? getHighlightLang(artifact) : 'text';

              return (
                <div
                  key={artifact.id}
                  className="glass-card-accent group"
                >
                  {/* Title bar */}
                  <div
                    className="flex items-center gap-1 px-3 py-2.5 cursor-pointer select-none"
                    onClick={() => setExpandedId(isExpanded ? null : artifact.id)}
                  >
                    <ChevronDown
                      className={cn(
                        'w-3.5 h-3.5 shrink-0 transition-transform duration-200',
                        isExpanded && 'rotate-180',
                      )}
                      style={{ color: 'var(--color-text-muted)' }}
                    />
                    <div className="flex-1 min-w-0">
                      <span className="text-[12px] font-semibold truncate block">
                        {artifact.title}
                      </span>
                      {artifact.language && (
                        <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                          {artifact.language}
                        </span>
                      )}
                    </div>
                    <button
                      className="w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-hover ml-1"
                      onClick={(e) => handleDelete(e, artifact.id)}
                      aria-label={`删除 ${artifact.title}`}
                    >
                      <X className="w-3 h-3" style={{ color: 'var(--color-text-muted)' }} />
                    </button>
                  </div>

                  {/* Export Word button */}
                  {(activeTab === 'code' || activeTab === 'doc') && (
                    <div className="px-3 pb-2 flex justify-end gap-2">
                      <button
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md transition-all hover:opacity-80"
                        style={{
                          background: 'rgba(184,192,255,0.08)',
                          color: 'var(--color-holo)',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          exportToWord(artifact);
                        }}
                        title="导出为 Word 文档"
                      >
                        <Download className="w-3 h-3" />
                        Word
                      </button>
                      <button
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md transition-all hover:opacity-80"
                        style={{
                          background: 'rgba(0,255,136,0.08)',
                          color: 'var(--color-mint)',
                        }}
                        onClick={(e) => handleSaveToKnowledge(e, artifact)}
                        disabled={savingToKnowledge === artifact.id}
                        title="一键存入知识库"
                      >
                        <BookOpen className="w-3 h-3" />
                        {savingToKnowledge === artifact.id ? '保存中…' : '知识库'}
                      </button>
                    </div>
                  )}

                  {/* Content — doc: render markdown with ReactMarkdown */}
                  {activeTab === 'doc' && (
                    <div
                      className={cn(
                        'overflow-hidden transition-all duration-300',
                        isExpanded ? 'max-h-[600px]' : 'max-h-[100px]',
                      )}
                    >
                      <div
                        className="prose prose-sm max-w-none p-3 rounded-b-lg overflow-y-auto"
                        style={{
                          background: 'var(--color-bg-tertiary)',
                          border: '1px solid var(--color-border)',
                          borderTop: 'none',
                          borderRadius: '0 0 8px 8px',
                          maxHeight: isExpanded ? '580px' : '80px',
                        }}
                      >
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                        >
                          {artifact.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}

                  {/* Content — image preview */}
                  {activeTab === 'image' && (
                    <div
                      className={cn(
                        'overflow-hidden transition-all duration-300',
                        isExpanded ? 'max-h-[500px]' : 'max-h-[100px]',
                      )}
                    >
                      {imgErrors.has(artifact.id) ? (
                        <div
                          className="flex items-center justify-center p-8 rounded-b-lg"
                          style={{
                            background: 'var(--color-bg-tertiary)',
                            border: '1px solid var(--color-border)',
                            borderTop: 'none',
                          }}
                        >
                          <Image className="w-12 h-12" style={{ color: 'var(--color-text-muted)' }} />
                        </div>
                      ) : (
                        <img
                          src={artifact.content}
                          alt={artifact.title}
                          className="w-full object-contain rounded-b-lg"
                          style={{
                            background: 'var(--color-bg-tertiary)',
                            border: '1px solid var(--color-border)',
                            borderTop: 'none',
                            maxHeight: '500px',
                          }}
                          onError={() => setImgErrors((prev) => new Set(prev).add(artifact.id))}
                        />
                      )}
                    </div>
                  )}

                  {/* Footer */}
                  <div className="flex items-center justify-between px-3 pb-2">
                    <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                      {artifact.created_at ? new Date(artifact.created_at).toLocaleTimeString() : ''}
                    </span>
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-medium uppercase"
                      style={{
                        background: 'rgba(184,192,255,0.08)',
                        color: 'var(--color-holo)',
                      }}
                    >
                      {artifact.type}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer stats */}
        <div
          className="shrink-0 flex items-center justify-between px-4 py-2.5"
          style={{ borderTop: '1px solid var(--color-border-glass)' }}
        >
          <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
            {artifacts.length} 个制品
          </span>
          <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
            {isLoading ? 'loading…' : 'live'}
          </span>
        </div>
      </aside>
    </>
  );
}
