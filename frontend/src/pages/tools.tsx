import { useState, useEffect, useCallback } from 'react';
import { Zap, Plus, Trash2, Search, Shield, Terminal, Braces, X } from 'lucide-react';
import { Badge } from '@/components/shared/badge';
import { ListSkeleton } from '@/components/shared/skeleton';
import { EmptyState } from '@/components/shared/empty-state';

interface ToolParam { name: string; type: string; description: string; required: boolean; }
interface Tool { name: string; description: string; parameters: ToolParam[]; toolset: string; requires_env: string[]; call_count: number; enabled: boolean; command?: string; }

// Toolset → Chinese label
const TOOLSET_LABELS: Record<string, string> = {
  browser: '浏览器',
  terminal: '终端',
  file: '文件',
  web: '网络',
  search: '搜索',
  memory: '记忆',
  session_search: '会话搜索',
  delegation: '代理',
  cronjob: '计划任务',
  code_execution: '代码执行',
  clarify: '询问',
  messaging: '消息',
  todo: '任务',
  vision: '视觉',
  tts: '语音',
  skills: '技能',
  spotify: 'Spotify',
  homeassistant: '智能家居',
  discord: 'Discord',
  discord_admin: 'Discord 管理',
  feishu_doc: '飞书文档',
  feishu_drive: '飞书云盘',
  yuanbao: '元宝',
};

const EMPTY_FORM = { name: '', description: '', toolset: '', paramsJson: '', command: '' };

export function ToolsPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [selectedToolset, setSelectedToolset] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [addLoading, setAddLoading] = useState(false);
  const [formError, setFormError] = useState('');

  // Fetch tools
  const fetchTools = useCallback(async () => {
    setError('');
    try {
      const r = await fetch('/api/v1/tools');
      const d = await r.json();
      const list = d.data?.tools || d.tools || [];
      setTools(list);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  const toolsets = [...new Set(tools.map(t => t.toolset))].sort();

  const filtered = tools.filter(t => {
    if (search && !t.name.includes(search) && !t.description.includes(search)) return false;
    if (selectedToolset && t.toolset !== selectedToolset) return false;
    return true;
  });

  const openAdd = () => {
    setForm(EMPTY_FORM);
    setFormError('');
    setShowAdd(true);
  };

  const handleAdd = async () => {
    setFormError('');
    if (!form.name.trim()) { setFormError('工具名称为必填项'); return; }

    // Parse params JSON
    let parameters: ToolParam[] = [];
    if (form.paramsJson.trim()) {
      try {
        const parsed = JSON.parse(form.paramsJson);
        if (!Array.isArray(parsed)) throw new Error('参数必须是数组格式');
        parameters = parsed;
      } catch {
        setFormError('参数 JSON 格式有误，请检查');
        return;
      }
    }

    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      toolset: form.toolset.trim(),
      parameters,
      command: form.command.trim(),
    };

    setAddLoading(true);
    try {
      await fetch('/api/v1/tools', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      setShowAdd(false);
      setLoading(true);
      await fetchTools();
    } catch (e: any) {
      setFormError('添加失败: ' + (e.message || '未知错误'));
    }
    setAddLoading(false);
  };

  const handleDelete = async (name: string) => {
    try {
      await fetch(`/api/v1/tools/${name}`, { method: 'DELETE' });
      setLoading(true);
      await fetchTools();
    } catch (e: any) {
      setError('删除失败: ' + (e.message || '未知错误'));
    }
  };

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
            value={selectedToolset}
            onChange={e => setSelectedToolset(e.target.value)}
            className="text-[13px]"
          >
            <option value="">全部工具集</option>
            {toolsets.map(ts => (
              <option key={ts} value={ts}>{TOOLSET_LABELS[ts] || ts}</option>
            ))}
          </select>
          <button className="btn-primary h-8 text-[12px]" onClick={openAdd}>
            <Plus className="w-3.5 h-3.5" />
            添加工具
          </button>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-2 mb-3 text-[12px] text-muted">
          <span>共 {filtered.length} 个工具</span>
          <span>·</span>
          <span>{toolsets.length} 个工具集</span>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-danger/10 text-danger text-[13px] p-3 rounded-lg mb-4">{error}</div>
        )}

        {/* Add form */}
        {showAdd && (
          <div className="glass-card-accent p-4 mb-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-[13px] font-semibold">添加新工具</h3>
              <button className="btn-ghost h-7 w-7 p-0" onClick={() => setShowAdd(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>

            {formError && (
              <div className="bg-danger/10 text-danger text-[12px] p-2 rounded-md">{formError}</div>
            )}

            {/* Row 1: name / toolset */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-muted mb-0.5 block">工具名称 *</label>
                <input
                  className="w-full"
                  placeholder="如 my_custom_tool"
                  value={form.name}
                  onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-[11px] text-muted mb-0.5 block">所属工具集</label>
                <input
                  className="w-full"
                  placeholder="如 terminal"
                  value={form.toolset}
                  onChange={e => setForm(p => ({ ...p, toolset: e.target.value }))}
                />
              </div>
            </div>

            {/* Row 2: description */}
            <div>
              <label className="text-[11px] text-muted mb-0.5 block">描述</label>
              <input
                className="w-full"
                placeholder="工具功能描述"
                value={form.description}
                onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
              />
            </div>

            {/* Row 3: parameters (JSON) + command side by side */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-muted mb-0.5 flex items-center gap-1">
                  <Braces className="w-3 h-3" />
                  参数定义 (JSON)
                </label>
                <textarea
                  className="w-full font-mono text-[11px]"
                  rows={4}
                  placeholder={'[\n  {"name": "url", "type": "string", "description": "目标地址", "required": true},\n  {"name": "timeout", "type": "number", "description": "超时", "required": false}\n]'}
                  value={form.paramsJson}
                  onChange={e => setForm(p => ({ ...p, paramsJson: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-[11px] text-muted mb-0.5 flex items-center gap-1">
                  <Terminal className="w-3 h-3" />
                  执行命令
                </label>
                <textarea
                  className="w-full font-mono text-[11px]"
                  rows={4}
                  placeholder="工具实际执行的命令，如：curl -X POST {url}"
                  value={form.command}
                  onChange={e => setForm(p => ({ ...p, command: e.target.value }))}
                />
              </div>
            </div>

            <div className="flex gap-2">
              <button className="btn-primary h-8 text-[12px]" onClick={handleAdd} disabled={addLoading}>
                {addLoading ? '添加中...' : '确认添加'}
              </button>
              <button className="btn-ghost h-8 text-[12px]" onClick={() => setShowAdd(false)}>取消</button>
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
                  <th>工具名称</th>
                  <th>参数</th>
                  <th>权限</th>
                  <th>调用次数</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(tool => (
                  <tr key={tool.name} className="border-b border-color/30 hover:bg-hover/30 transition-colors">
                    <td>
                      <div>
                        <span className="text-[13px] font-medium">{tool.name}</span>
                        <p className="text-[11px] text-muted mt-0.5 max-w-[240px] truncate">
                          {tool.description}
                        </p>
                        {tool.command && (
                          <p className="text-[10px] text-muted mt-0.5 max-w-[240px] truncate font-mono">
                            <Terminal className="w-2.5 h-2.5 inline mr-0.5" />
                            {tool.command}
                          </p>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {tool.parameters && tool.parameters.length > 0 ? (
                          tool.parameters.map(p => (
                            <span key={p.name} className="text-[11px] text-muted">
                              <code className="text-[10px]">{p.name}</code>
                              {p.required && <span className="text-accent ml-0.5">*</span>}
                            </span>
                          ))
                        ) : (
                          <span className="text-[11px] text-muted">-</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        <Badge variant="info">{TOOLSET_LABELS[tool.toolset] || tool.toolset || '默认'}</Badge>
                        {tool.requires_env && tool.requires_env.length > 0 && (
                          <span className="flex items-center gap-0.5 text-[10px] text-warning" title={tool.requires_env.join(', ')}>
                            <Shield className="w-2.5 h-2.5" />
                            需 API Key
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className="text-[13px] font-mono">{tool.call_count ?? 0}</span>
                    </td>
                    <td>
                      <button
                        className="btn-ghost h-7 w-7 p-0 flex items-center justify-center text-danger hover:bg-danger/10"
                        onClick={() => handleDelete(tool.name)}
                        title="删除工具"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
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
