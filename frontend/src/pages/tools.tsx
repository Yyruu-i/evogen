import { useState, useEffect, useCallback } from 'react';
import { Zap, Plus, Trash2, Search, Terminal, Pencil, X, CheckSquare, Square, FileDown } from 'lucide-react';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';

// ── Types ──────────────────────────────────────────────────────

interface ToolEntry {
  id: string;
  name: string;
  description: string;
  endpoint: string;
  category: string;
  parameters: Record<string, string>;
  user_id?: string;
  scope: 'builtin' | 'user';
  created_at: string;
}

interface ToolForm {
  name: string;
  description: string;
  endpoint: string;
  category: string;
  paramsJson: string;
}

// ── Chinese labels ─────────────────────────────────────────────

const CATEGORY_LABELS_CN: Record<string, string> = {
  '联网': '联网搜索',
  '浏览器': '浏览器',
  '终端': '终端命令',
  '文件': '文件操作',
  '网络': '网络请求',
  '搜索': '搜索',
  '内存': '内存',
  '记忆': '记忆',
  '代理': '代理任务',
  '代码执行': '代码执行',
  '计划任务': '计划任务',
  '测试': '测试',
  'AI': 'AI 对话',
  '消息': '消息推送',
};

const TOOL_NAME_CN: Record<string, string> = {
  'web_search': '网页搜索',
  'browser': '浏览器',
  'port_scan': '端口扫描 (nmap)',
  'vuln_scan': '漏洞扫描 (Nuclei)',
  'rkhunter_scan': 'Rootkit 检测 (rkhunter)',
  'chkrootkit_scan': 'Rootkit 检测 (chkrootkit)',
  'clamav_scan': '病毒扫描 (ClamAV)',
};

function categoryLabel(cat: string): string {
  return CATEGORY_LABELS_CN[cat] || cat;
}

function toolNameLabel(name: string): string {
  return TOOL_NAME_CN[name] || name;
}

// ── API helpers ────────────────────────────────────────────────

const AUTH_TOKEN_KEY = 'evogen-auth-token';
function getToken(): string {
  try { return localStorage.getItem(AUTH_TOKEN_KEY) || ''; }
  catch { return ''; }
}

async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = typeof body.detail === 'object'
      ? (body.detail?.error || JSON.stringify(body.detail))
      : (body.detail || body.error);
    throw new Error(msg || `HTTP ${res.status}`);
  }
  const json = await res.json();
  if (json.ok === true && 'data' in json) return json.data as T;
  return json as T;
}

// ── Constants ──────────────────────────────────────────────────

const EMPTY_FORM: ToolForm = {
  name: '', description: '', endpoint: '', category: '', paramsJson: '',
};

// ── Component ──────────────────────────────────────────────────

export function ToolsPage() {
  const [tools, setTools] = useState<ToolEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ToolForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  // Batch select state
  const [batchMode, setBatchMode] = useState(false);
  const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  // ── Fetch tools ──────────────────────────────────────────

  const fetchTools = useCallback(async () => {
    setError('');
    try {
      const data = await apiRequest<{ tools: ToolEntry[]; total: number }>('/resource/tools');
      setTools(data.tools || []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  // ── Derived data ─────────────────────────────────────────

  const categories = [...new Set(tools.map(t => t.category).filter(Boolean))].sort();
  const userTools = tools.filter(t => t.scope === 'user');

  const filtered = tools.filter(t => {
    if (search && !t.name.includes(search) && !t.description.includes(search)) return false;
    if (selectedCategory && t.category !== selectedCategory) return false;
    return true;
  });

  // ── Batch handlers ───────────────────────────────────────

  const exitBatchMode = () => {
    setBatchMode(false);
    setSelectedNames(new Set());
  };

  const toggleSelect = (name: string) => {
    setSelectedNames(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  const handleSelectAll = () => {
    const userNames = userTools.map(t => t.name);
    if (selectedNames.size === userTools.length && userTools.length > 0) {
      setSelectedNames(new Set());
    } else {
      setSelectedNames(new Set(userNames));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedNames.size === 0) { alert('请先选择要删除的工具'); return; }
    setBatchDeleting(true);
    try {
      await apiRequest('/tools/batch/delete', {
        method: 'POST',
        body: JSON.stringify({ names: [...selectedNames] }),
      });
      exitBatchMode();
      setLoading(true);
      await fetchTools();
    } catch (e: any) {
      alert('批量删除失败: ' + (e.message || '未知错误'));
    }
    setBatchDeleting(false);
  };

  // ── Form handlers ────────────────────────────────────────

  const openAdd = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError('');
    setShowForm(true);
  };

  const openEdit = (tool: ToolEntry) => {
    setEditingId(tool.id);
    setForm({
      name: tool.name,
      description: tool.description,
      endpoint: tool.endpoint,
      category: tool.category,
      paramsJson: tool.parameters && Object.keys(tool.parameters).length > 0
        ? JSON.stringify(tool.parameters, null, 2)
        : '',
    });
    setFormError('');
    setShowForm(true);
  };

  const handleSave = async () => {
    setFormError('');
    if (!form.name.trim()) { setFormError('工具名称为必填项'); return; }

    let parameters: Record<string, string> = {};
    if (form.paramsJson.trim()) {
      try {
        parameters = JSON.parse(form.paramsJson);
        if (typeof parameters !== 'object' || Array.isArray(parameters)) {
          throw new Error('参数必须是 JSON 对象');
        }
      } catch {
        setFormError('参数 JSON 格式有误，请检查');
        return;
      }
    }

    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      endpoint: form.endpoint.trim(),
      category: form.category.trim(),
      parameters,
    };

    setSaving(true);
    try {
      if (editingId) {
        await apiRequest(`/resource/tools/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiRequest('/resource/tools', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      setShowForm(false);
      setLoading(true);
      await fetchTools();
    } catch (e: any) {
      setFormError('保存失败: ' + (e.message || '未知错误'));
    }
    setSaving(false);
  };

  const handleDelete = async (toolId: string) => {
    try {
      await apiRequest(`/resource/tools/${toolId}`, { method: 'DELETE' });
      setLoading(true);
      await fetchTools();
    } catch (e: any) {
      setError('删除失败: ' + (e.message || '未知错误'));
    }
  };

  // ── Render ───────────────────────────────────────────────

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
          <Zap className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h1 className="text-[15px] font-semibold text-primary">工具管理</h1>
        </div>
      </header>

      <main className="flex flex-col flex-1 p-4 md:p-6 max-w-6xl mx-auto w-full">
        {/* Toolbar */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-[320px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
            <input
              className="w-full pl-8 pr-3"
              placeholder="搜索工具..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <select
            value={selectedCategory}
            onChange={e => setSelectedCategory(e.target.value)}
            className="text-[13px]"
          >
            <option value="">全部分类</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{categoryLabel(cat)}</option>
            ))}
          </select>

          {batchMode ? (
            <div className="flex items-center gap-2">
              <span className="text-[12px] text-muted">已选 {selectedNames.size}/{userTools.length}</span>
              <button className="btn-ghost h-7 text-[12px]" onClick={handleSelectAll}>
                {selectedNames.size === userTools.length && userTools.length > 0
                  ? <Square className="w-3.5 h-3.5" />
                  : <CheckSquare className="w-3.5 h-3.5" />
                }
                {selectedNames.size === userTools.length && userTools.length > 0 ? '取消全选' : '全选'}
              </button>
              <button
                className="btn-primary h-7 text-[12px] text-danger"
                onClick={handleBatchDelete}
                disabled={selectedNames.size === 0 || batchDeleting}
                style={{ background: 'var(--color-danger)', color: '#fff' }}
              >
                <Trash2 className="w-3.5 h-3.5" />
                {batchDeleting ? '删除中...' : '批量删除'}
              </button>
              <button className="btn-ghost h-7 text-[12px]" onClick={exitBatchMode}>
                <X className="w-3.5 h-3.5" />
                取消
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button className="btn-ghost h-7 text-[12px]" onClick={() => setBatchMode(true)}>
                <CheckSquare className="w-3.5 h-3.5" />
                批量操作
              </button>
              <button className="btn-primary h-8 text-[12px]" onClick={openAdd}>
                <Plus className="w-3.5 h-3.5" />
                添加工具
              </button>
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="flex items-center gap-2 mb-3 text-[12px] text-muted">
          <span>共 {filtered.length} 个工具</span>
          <span>·</span>
          <span>{tools.filter(t => t.scope === 'builtin').length} 个内置</span>
          <span>·</span>
          <span>{tools.filter(t => t.scope === 'user').length} 个自定义</span>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-danger/10 text-danger text-[13px] p-3 rounded-lg mb-4">{error}</div>
        )}

        {/* Add/Edit modal */}
        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="glass-card-accent p-6 w-full max-w-lg mx-4 space-y-4 max-h-[85vh] overflow-y-auto">
              <div className="flex items-center justify-between">
                <h3 className="text-[15px] font-semibold">
                  {editingId ? '编辑工具' : '添加工具'}
                </h3>
                <button className="btn-ghost h-7 w-7 p-0" onClick={() => setShowForm(false)}>
                  <X className="w-4 h-4" />
                </button>
              </div>

              {formError && (
                <div className="bg-danger/10 text-danger text-[12px] p-2 rounded-md">{formError}</div>
              )}

              <div className="space-y-3">
                <div>
                  <label className="text-[11px] text-muted mb-0.5 block">工具名称 *</label>
                  <input
                    className="w-full"
                    placeholder="如 web_search"
                    value={form.name}
                    onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                  />
                </div>

                <div>
                  <label className="text-[11px] text-muted mb-0.5 block">分类</label>
                  <input
                    className="w-full"
                    placeholder="如 网络"
                    value={form.category}
                    onChange={e => setForm(p => ({ ...p, category: e.target.value }))}
                  />
                </div>

                <div>
                  <label className="text-[11px] text-muted mb-0.5 block">描述</label>
                  <input
                    className="w-full"
                    placeholder="工具功能描述"
                    value={form.description}
                    onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                  />
                </div>

                <div>
                  <label className="text-[11px] text-muted mb-0.5 flex items-center gap-1">
                    <Terminal className="w-3 h-3" />
                    端点/命令
                  </label>
                  <input
                    className="w-full font-mono text-[12px]"
                    placeholder="如 /api/v1/search 或 curl -X POST {url}"
                    value={form.endpoint}
                    onChange={e => setForm(p => ({ ...p, endpoint: e.target.value }))}
                  />
                </div>

                <div>
                  <label className="text-[11px] text-muted mb-0.5 block">参数定义 (JSON)</label>
                  <textarea
                    className="w-full font-mono text-[11px]"
                    rows={4}
                    placeholder='{"query": "string", "limit": "int"}'
                    value={form.paramsJson}
                    onChange={e => setForm(p => ({ ...p, paramsJson: e.target.value }))}
                  />
                </div>
              </div>

              <div className="flex gap-2 pt-2">
                <button className="btn-primary h-8 text-[12px]" onClick={handleSave} disabled={saving}>
                  {saving ? '保存中...' : editingId ? '更新工具' : '创建工具'}
                </button>
                <button className="btn-ghost h-8 text-[12px]" onClick={() => setShowForm(false)}>取消</button>
              </div>
            </div>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <ListSkeleton rows={8} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Zap}
            title="暂无工具"
            description="工具帮助 Agent 与外部系统交互。点击「添加工具」注册新工具。"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  {batchMode && <th style={{ width: 32 }}></th>}
                  <th>工具名称</th>
                  <th>分类</th>
                  <th>端点</th>
                  <th>类型</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(tool => (
                  <tr key={tool.id} className="border-b border-color/30 hover:bg-hover/30 transition-colors">
                    {batchMode && (
                      <td className="text-center">
                        {tool.scope === 'user' ? (
                          <input
                            type="checkbox"
                            className="w-4 h-4 cursor-pointer"
                            checked={selectedNames.has(tool.name)}
                            onChange={() => toggleSelect(tool.name)}
                          />
                        ) : null}
                      </td>
                    )}
                    <td>
                      <div>
                        <span className="text-[13px] font-medium">{toolNameLabel(tool.name)}</span>
                        <p className="text-[11px] text-muted mt-0.5 max-w-[240px] truncate">
                          {tool.description}
                        </p>
                      </div>
                    </td>
                    <td>
                      <span className="text-[12px]">{categoryLabel(tool.category)}</span>
                    </td>
                    <td>
                      <code className="text-[11px] text-muted max-w-[200px] truncate block">
                        {tool.endpoint || '-'}
                      </code>
                    </td>
                    <td>
                      <Badge variant={tool.scope === 'builtin' ? 'accent' : 'default'}>
                        {tool.scope === 'builtin' ? '内置' : '用户'}
                      </Badge>
                    </td>
                    <td>
                      {tool.scope === 'user' ? (
                        <div className="flex gap-1">
                          <button
                            className="btn-ghost h-7 text-[11px] px-2"
                            onClick={() => openEdit(tool)}
                            title="编辑工具"
                          >
                            <Pencil className="w-3 h-3" />
                          </button>
                          <button
                            className="btn-ghost h-7 text-[11px] px-2 text-danger hover:bg-danger/10"
                            onClick={() => handleDelete(tool.id)}
                            title="删除工具"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-[11px] text-muted">只读</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
