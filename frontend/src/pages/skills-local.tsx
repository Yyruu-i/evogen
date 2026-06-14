import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/auth-context';
import { useSkills } from '@/hooks/use-skills';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';
import {
  Wrench, Plus, Pencil, Trash2, Download, Upload, FileDown, CheckSquare,
  Square, X,
} from 'lucide-react';
import { skillLabel, SKILL_NAME_CN, SKILL_CATEGORY_CN, SKILL_TAG_CN } from '@/lib/utils';

interface SkillFormData {
  name: string;
  category: string;
  description: string;
  markdown: string;
}

const EMPTY_FORM: SkillFormData = { name: '', category: '', description: '', markdown: '' };

// ── 英→中 映射 ──
const CATEGORY_CN: Record<string, string> = {
  'software-development': '开发', 'autonomous-ai-agents': 'AI 代理', 'creative': '创作',
  'data-science': '数据科学', 'devops': '运维', 'dogfood': '测试', 'email': '邮件',
  'gaming': '游戏', 'github': 'GitHub', 'mcp': 'MCP', 'media': '媒体',
  'mlops': 'MLOps', 'note-taking': '笔记', 'productivity': '效率',
  'red-teaming': '安全测试', 'research': '研究', 'smart-home': '智能家居',
  'social-media': '社交媒体', 'uncategorized': '未分类',
};
function cnCat(cat: string): string { return CATEGORY_CN[cat] || cat; }

// ── API helper ──
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

export function SkillsLocalPage() {
  const navigate = useNavigate();
  const { data, isLoading, refetch } = useSkills();
  const { token } = useAuth();
  const skills = data?.skills || [];
  const total = data?.total ?? skills.length;

  // ── 用户切换时自动刷新技能列表 ──
  useEffect(() => {
    refetch();
  }, [token, refetch]);

  // Modal & form state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<SkillFormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // Batch select state
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const openAdd = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const openEdit = async (skill: any) => {
    setEditingId(skill.id);
    // 读取技能详情，获取 markdown 正文
    let markdownBody = '';
    try {
      const detail = await apiRequest<{ content: string }>(`/skills/${skill.id}`);
      markdownBody = detail.content || '';
    } catch {
      // fallback
    }
    setForm({
      name: skill.name || '',
      category: skill.category || '',
      description: skill.description || '',
      markdown: markdownBody,
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        await apiRequest(`/skills/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: form.name,
            description: form.description,
            category: form.category,
            markdown: form.markdown,
          }),
        });
      } else {
        await apiRequest('/skills', {
          method: 'POST',
          body: JSON.stringify({
            name: form.name,
            description: form.description,
            category: form.category,
            markdown: form.markdown,
          }),
        });
      }
      setShowForm(false);
      refetch();
    } catch (e: any) {
      alert('保存失败: ' + (e.message || '未知错误'));
    }
    setSaving(false);
  };

  const handleDelete = async (skillId: string) => {
    try {
      await apiRequest(`/skills/${skillId}`, { method: 'DELETE' });
      refetch();
    } catch (e: any) {
      alert('删除失败: ' + (e.message || '未知错误'));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) { alert('请先选择要删除的技能'); return; }
    try {
      await apiRequest('/skills/batch/delete', {
        method: 'POST',
        body: JSON.stringify({ ids: [...selectedIds] }),
      });
      setBatchMode(false);
      setSelectedIds(new Set());
      refetch();
    } catch (e: any) {
      alert('批量删除失败: ' + (e.message || '未知错误'));
    }
  };

  const handleExportSingle = (skill: any) => {
    const blob = new Blob([JSON.stringify(skill, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `skill-${skill.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleBatchExport = () => {
    const selected = skills.filter(s => selectedIds.has(s.id));
    if (selected.length === 0) { alert('请先选择要导出的技能'); return; }
    const blob = new Blob([JSON.stringify(selected, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `skills-export-${selected.length}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setBatchMode(false);
    setSelectedIds(new Set());
  };

  const handleSelectAll = () => {
    if (selectedIds.size === skills.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(skills.map(s => s.id)));
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const fname = file.name.toLowerCase();

      if (fname.endsWith('.zip')) {
        // Zip 导入：解析为 JSON 列表导入
        throw new Error('ZIP 导入请在服务器端执行');
      } else if (fname.endsWith('.md')) {
        // Markdown 导入，从 frontmatter 解析
        const lines = text.split('\n');
        let name = '', description = '', category = '', body = text;
        if (text.startsWith('---')) {
          const parts = text.split('---', 3);
          if (parts.length >= 3) {
            const fmLines = parts[1].split('\n');
            for (const l of fmLines) {
              if (l.startsWith('name:')) name = l.replace('name:', '').trim();
              if (l.startsWith('description:')) description = l.replace('description:', '').trim();
              if (l.startsWith('category:')) category = l.replace('category:', '').trim();
            }
            body = parts[2].trim();
          }
        }
        await apiRequest('/skills', {
          method: 'POST',
          body: JSON.stringify({ name, description, category, markdown: body }),
        });
      } else {
        // JSON 导入
        const data = JSON.parse(text);
        const items = Array.isArray(data) ? data : [data];
        for (const item of items) {
          await apiRequest('/skills', {
            method: 'POST',
            body: JSON.stringify(item),
          });
        }
      }
      refetch();
      alert('导入成功');
    } catch (e: any) {
      alert('导入失败: ' + (e.message || '文件格式错误'));
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const exitBatchMode = () => {
    setBatchMode(false);
    setSelectedIds(new Set());
  };

  return (
    <div className="max-w-4xl">
      {/* Header + actions */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-[15px] font-semibold">本地技能</h3>
          <span className="text-[12px] text-muted">共 {total} 个技能</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {batchMode ? (
            <>
              <span className="text-[12px] text-muted">已选 {selectedIds.size}/{skills.length}</span>
              <button className="btn-ghost h-7 text-[12px]" onClick={handleSelectAll}>
                {selectedIds.size === skills.length ? <Square className="w-3.5 h-3.5" /> : <CheckSquare className="w-3.5 h-3.5" />}
                {selectedIds.size === skills.length ? '取消全选' : '全选'}
              </button>
              <button className="btn-primary h-7 text-[12px]" onClick={handleBatchExport} disabled={selectedIds.size === 0}>
                <FileDown className="w-3.5 h-3.5" />
                批量导出
              </button>
              <button className="btn-primary h-7 text-[12px] text-danger" onClick={handleBatchDelete} disabled={selectedIds.size === 0}
                style={{ background: 'var(--color-danger)', color: '#fff' }}
              >
                <Trash2 className="w-3.5 h-3.5" />
                批量删除
              </button>
              <button className="btn-ghost h-7 text-[12px]" onClick={exitBatchMode}>
                <X className="w-3.5 h-3.5" />
                取消
              </button>
            </>
          ) : (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,.md,.zip"
                onChange={handleImport}
                className="hidden"
              />
              <button className="btn-ghost h-7 text-[12px]" onClick={() => setBatchMode(true)}>
                <CheckSquare className="w-3.5 h-3.5" />
                批量操作
              </button>
              <button className="btn-ghost h-7 text-[12px]" onClick={() => fileInputRef.current?.click()}>
                <Upload className="w-3.5 h-3.5" />
                导入
              </button>
              <button className="btn-primary h-7 text-[12px]" onClick={openAdd}>
                <Plus className="w-3.5 h-3.5" />
                添加技能
              </button>
            </>
          )}
        </div>
      </div>

      {/* Add/Edit Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card-accent p-6 w-full max-w-lg mx-4 space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-semibold">{editingId ? '编辑技能' : '添加技能'}</h3>
              <button className="btn-ghost h-7 w-7 p-0" onClick={() => setShowForm(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-[12px] text-muted mb-1 block">名称 *</label>
                <input
                  className="w-full"
                  placeholder="技能名称"
                  value={form.name}
                  onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-[12px] text-muted mb-1 block">分类</label>
                <input
                  className="w-full"
                  placeholder="如 software-development"
                  value={form.category}
                  onChange={e => setForm(p => ({ ...p, category: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-[12px] text-muted mb-1 block">描述</label>
                <textarea
                  className="w-full"
                  rows={2}
                  placeholder="技能描述"
                  value={form.description}
                  onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-[12px] text-muted mb-1 block">Markdown 正文</label>
                <textarea
                  className="w-full font-mono text-[12px]"
                  rows={8}
                  placeholder="技能 Markdown 内容..."
                  value={form.markdown}
                  onChange={e => setForm(p => ({ ...p, markdown: e.target.value }))}
                />
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <button className="btn-primary h-8 text-[13px]" onClick={handleSave} disabled={saving}>
                {saving ? '保存中...' : editingId ? '更新技能' : '创建技能'}
              </button>
              <button className="btn-ghost h-8 text-[13px]" onClick={() => setShowForm(false)}>取消</button>
            </div>
          </div>
        </div>
      )}

      {/* Skills table — matching tools table style */}
      {isLoading ? (
        <ListSkeleton rows={5} />
      ) : skills.length === 0 ? (
        <EmptyState
          icon={Wrench}
          title="暂无本地技能"
          description="技能帮助 Agent 完成特定任务。你可以从技能市场安装新技能，或手动添加。"
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                {batchMode && <th style={{ width: 32 }}></th>}
                <th>技能名称</th>
                <th>分类</th>
                <th>描述</th>
                <th>类型</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {skills.map((skill) => (
                <tr key={skill.id} className="border-b border-color/30 hover:bg-hover/30 transition-colors">
                  {batchMode && (
                    <td>
                      <button
                        className="btn-ghost h-7 w-7 p-0"
                        onClick={(e) => { e.stopPropagation(); toggleSelect(skill.id); }}
                      >
                        {selectedIds.has(skill.id) ? (
                          <CheckSquare className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
                        ) : (
                          <Square className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                        )}
                      </button>
                    </td>
                  )}
                  <td>
                    <div>
                      <span
                        className="text-[13px] font-medium cursor-pointer"
                        onClick={() => !batchMode && navigate(`/skills/local/${skill.id}`)}
                      >
                        {skillLabel(skill.name, SKILL_NAME_CN)}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className="text-[12px]">{cnCat(skill.category)}</span>
                  </td>
                  <td>
                    <p className="text-[11px] text-muted mt-0.5 max-w-[240px] truncate">
                      {skillLabel(skill.description, SKILL_NAME_CN)}
                    </p>
                  </td>
                  <td>
                    <Badge variant={skill.scope === 'builtin' ? 'accent' : 'default'}>
                      {skill.scope === 'builtin' ? '内置' : '用户'}
                    </Badge>
                  </td>
                  <td>
                    {skill.scope === 'builtin' ? (
                      <span className="text-[11px] text-muted">只读</span>
                    ) : (
                      <div className="flex gap-1">
                        <button
                          className="btn-ghost h-7 text-[11px] px-2"
                          onClick={() => openEdit(skill)}
                          title="编辑"
                        >
                          <Pencil className="w-3 h-3" />
                          编辑
                        </button>
                        <button
                          className="btn-ghost h-7 text-[11px] px-2"
                          onClick={() => handleExportSingle(skill)}
                          title="导出"
                        >
                          <Download className="w-3 h-3" />
                        </button>
                        <button
                          className="btn-ghost h-7 text-[11px] px-2 text-danger hover:bg-danger/10"
                          onClick={() => handleDelete(skill.id)}
                          title="删除"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
