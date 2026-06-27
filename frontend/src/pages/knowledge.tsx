import { useState, useRef, useCallback, useEffect } from 'react';
import { BookOpen, Search, Upload, FileText, Trash2, Loader2, X } from 'lucide-react';

// ── API helpers ────────────────────────────────────────────────

const AUTH_TOKEN_KEY = 'evogen-auth-token';
function getToken(): string {
  try { return localStorage.getItem(AUTH_TOKEN_KEY) || ''; }
  catch { return ''; }
}

interface KnowledgeEntry {
  id: string;
  content: string;
  source: string;
  created_at: string;
}

async function apiGet<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`/api/v1${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Component ──────────────────────────────────────────────────

export function KnowledgePage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<KnowledgeEntry[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchEntries = useCallback(async () => {
    setError('');
    try {
      const data = await apiGet<{ entries: KnowledgeEntry[]; total: number }>('/knowledge');
      setEntries(data.entries || []);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    setError('');
    try {
      const data = await apiPost<{ results: KnowledgeEntry[] }>('/knowledge/search', { query: searchQuery, limit: 20 });
      setSearchResults(data.results || []);
    } catch (e: any) {
      setError(e.message || '搜索失败');
    } finally {
      setSearching(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const text = await file.text();
      await apiPost('/knowledge/upload', { content: text, source: file.name });
      await fetchEntries();
    } catch (e: any) {
      setError(e.message || '上传失败');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiPost('/knowledge/delete', { id });
      setEntries(prev => prev.filter(e => e.id !== id));
    } catch (e: any) {
      setError(e.message || '删除失败');
    }
  };

  const displayEntries = searchResults ?? entries;

  return (
    <div className="flex flex-col min-h-full bg-primary">
      <header
        className="h-14 md:h-16 flex items-center flex-shrink-0 p-4 md:px-6"
        style={{
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid var(--color-border-glass)',
        }}
      >
        <div className="flex items-center gap-3">
          <BookOpen className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h1 className="text-[15px] font-semibold text-primary">知识库</h1>
        </div>
      </header>

      <main className="flex flex-col flex-1 p-4 md:p-6 max-w-4xl mx-auto w-full">
        {/* Search + Upload bar */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-[400px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
            <input
              className="w-full pl-8 pr-3 h-9 text-[13px] rounded-lg"
              placeholder="搜索知识库..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              style={{
                background: 'var(--color-bg-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              }}
            />
          </div>
          <button
            className="h-9 px-4 text-[12px] font-medium rounded-lg flex items-center gap-1.5"
            style={{
              background: 'rgba(184,192,255,0.08)',
              color: 'var(--color-holo)',
              border: '1px solid var(--color-border-glass)',
            }}
            onClick={handleSearch}
            disabled={searching}
          >
            {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            搜索
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.pdf,.docx,.csv,.json"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            className="h-9 px-4 text-[12px] font-medium rounded-lg flex items-center gap-1.5"
            style={{
              background: 'linear-gradient(135deg, var(--color-accent), var(--color-coral))',
              color: '#fff',
            }}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            {uploading ? '上传中...' : '上传文档'}
          </button>
        </div>

        {error && (
          <div className="text-[13px] p-3 rounded-lg mb-4" style={{ background: 'rgba(220,53,69,0.1)', color: 'var(--color-danger)' }}>
            {error}
          </div>
        )}

        {searchResults !== null && (
          <div className="flex items-center gap-2 mb-3 text-[12px]">
            <span style={{ color: 'var(--color-text-muted)' }}>搜索结果 ({searchResults.length} 条)</span>
            <button
              className="text-[12px] flex items-center gap-1"
              style={{ color: 'var(--color-accent)' }}
              onClick={() => { setSearchResults(null); setSearchQuery(''); }}
            >
              <X className="w-3 h-3" /> 清除
            </button>
          </div>
        )}

        {/* Entries list */}
        <div className="flex-1 overflow-y-auto space-y-2">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--color-text-muted)' }} />
            </div>
          ) : displayEntries.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-2">
              <BookOpen className="w-10 h-10" style={{ color: 'var(--color-text-muted)' }} />
              <span className="text-[13px]" style={{ color: 'var(--color-text-muted)' }}>
                {searchResults !== null ? '无搜索结果' : '知识库为空'}
              </span>
              <span className="text-[12px]" style={{ color: 'var(--color-text-muted)' }}>
                {searchResults !== null ? '尝试其他关键词' : '上传文档或内容至知识库'}
              </span>
            </div>
          ) : (
            displayEntries.map(entry => (
              <div
                key={entry.id}
                className="rounded-xl p-4 transition-all hover:shadow-sm"
                style={{
                  background: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <FileText className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                      <span className="text-[12px] font-medium truncate" style={{ color: 'var(--color-text-secondary)' }}>
                        {entry.source}
                      </span>
                    </div>
                    <p className="text-[13px] leading-relaxed line-clamp-3" style={{ color: 'var(--color-text-primary)' }}>
                      {entry.content}
                    </p>
                    <p className="text-[11px] mt-1" style={{ color: 'var(--color-text-muted)' }}>
                      {new Date(entry.created_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                  <button
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 hover:bg-hover transition-colors"
                    onClick={() => handleDelete(entry.id)}
                    title="删除"
                  >
                    <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
