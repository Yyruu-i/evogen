import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
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

export function SkillsLocalPage() {
  const navigate = useNavigate();
  const { data, isLoading, refetch } = useSkills();
  const skills = data?.skills || [];
  const total = data?.total ?? skills.length;

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

  const openEdit = (skill: any) => {
    setEditingId(skill.id);
    setForm({
      name: skill.name || '',
      category: skill.category || '',
      description: skill.description || '',
      markdown: '', // backend doesn't expose markdown body currently
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        // Update existing skill
        await fetch(`/api/v1/skills/${editingId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        });
      } else {
        // Create new skill
        await fetch('/api/v1/skills', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
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
      await fetch(`/api/v1/skills/${skillId}`, { method: 'DELETE' });
      refetch();
    } catch (e: any) {
      alert('删除失败: ' + (e.message || '未知错误'));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) { alert('请先选择要删除的技能'); return; }
    try {
      const res = await fetch('/api/v1/skills/batch/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: [...selectedIds] }),
      });
      const d = await res.json();
      if (d.ok) {
        setBatchMode(false);
        setSelectedIds(new Set());
        refetch();
      } else {
        alert('批量删除失败: ' + (d.error || '未知错误'));
      }
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
      const data = JSON.parse(text);
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        await fetch('/api/v1/skills', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(item),
        });
      }
      refetch();
      alert(`成功导入 ${items.length} 个技能`);
    } catch (e: any) {
      alert('导入失败: ' + (e.message || '文件格式错误'));
    }
    // Reset input so same file can be re-imported
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
                accept=".json"
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

      {/* Skills list */}
      {isLoading ? (
        <ListSkeleton rows={5} />
      ) : skills.length === 0 ? (
        <EmptyState
          icon={Wrench}
          title="暂无本地技能"
          description="技能帮助 Agent 完成特定任务。你可以从技能市场安装新技能，或手动添加。"
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {skills.map((skill) => (
            <div
              key={skill.id}
              className="glass-card-accent p-4 transition-transform duration-200 group relative"
            >
              {/* Batch select checkbox */}
              {batchMode && (
                <button
                  className="absolute top-2 right-2 z-10"
                  onClick={(e) => { e.stopPropagation(); toggleSelect(skill.id); }}
                >
                  {selectedIds.has(skill.id) ? (
                    <CheckSquare className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
                  ) : (
                    <Square className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
                  )}
                </button>
              )}

              <div
                className={batchMode ? '' : 'cursor-pointer'}
                onClick={() => batchMode ? toggleSelect(skill.id) : navigate(`/skills/local/${skill.id}`)}
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <h4 className="text-[13px] font-semibold text-truncate-safe">
                      {skillLabel(skill.name, SKILL_NAME_CN)}
                    </h4>
                    <p className="text-[12px] text-secondary mt-1 text-truncate-safe">
                      {skillLabel(skill.description, SKILL_NAME_CN)}
                    </p>
                  </div>
                  <Badge variant={skill.scope === 'builtin' ? 'accent' : skill.source === 'local' ? 'default' : 'accent'} className="ml-2 shrink-0">
                    {skill.scope === 'builtin' ? '内置' : skill.source === 'local' ? '本地' : skill.source === 'hub' ? '市场' : '自动生成'}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 mt-3 flex-wrap">
                  <span className="text-[11px] text-muted">v{skill.version}</span>
                  <span className="text-[11px] text-muted">使用 {skill.use_count} 次</span>
                  <span className="text-[11px] text-muted">
                    成功率 {Math.round(skill.success_rate * 100)}%
                  </span>
                  <span className="text-[11px] text-muted text-truncate-safe">
                    {skillLabel(skill.category, SKILL_CATEGORY_CN)}
                  </span>
                </div>
                {skill.tags && skill.tags.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {skill.tags.map((tag: string) => (
                      <Badge key={tag} variant="info">{skillLabel(tag, SKILL_TAG_CN)}</Badge>
                    ))}
                  </div>
                )}
              </div>

              {/* Action buttons — hidden for builtin skills and batch mode */}
              {!batchMode && skill.scope !== 'builtin' && (
                <div className="flex gap-1 mt-3 pt-2 border-t border-color/30 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    className="btn-ghost h-6 text-[11px] px-2"
                    onClick={(e) => { e.stopPropagation(); openEdit(skill); }}
                  >
                    <Pencil className="w-3 h-3" />
                    编辑
                  </button>
                  <button
                    className="btn-ghost h-6 text-[11px] px-2"
                    onClick={(e) => { e.stopPropagation(); handleExportSingle(skill); }}
                  >
                    <Download className="w-3 h-3" />
                    导出
                  </button>
                  <button
                    className="btn-ghost h-6 text-[11px] px-2 text-danger hover:bg-danger/10"
                    onClick={(e) => { e.stopPropagation(); handleDelete(skill.id); }}
                  >
                    <Trash2 className="w-3 h-3" />
                    删除
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
