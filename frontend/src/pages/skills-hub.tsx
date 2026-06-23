import { useState, useEffect } from 'react';
import { Globe, Star, Download, Search, MessageSquare, X, ChevronDown, ChevronUp } from 'lucide-react';
import { Skeleton } from '@/components/shared/skeleton';

interface MarketSkill {
  id: string;
  name: string;
  description: string;
  category: string;
  author: string;
  version: string;
  install_count: number;
  rating: number;
  tags: string[];
  review_count: number;
  updated_at: string;
}

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

export function SkillsHubPage() {
  const [skills, setSkills] = useState<MarketSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [installing, setInstalling] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [reviews, setReviews] = useState<any[]>([]);
  const [reviewForm, setReviewForm] = useState<{ rating: number; comment: string }>({ rating: 5, comment: '' });

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async (query?: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (query) params.set('search', query);
      const qs = params.toString();
      const data = await apiRequest<{ skills: MarketSkill[]; total: number }>(`/skills/market${qs ? '?' + qs : ''}`);
      setSkills(data.skills || []);
    } catch (e: any) {
      setMessage({ type: 'error', text: '加载失败: ' + (e.message || '') });
    }
    setLoading(false);
  };

  const handleSearch = () => {
    loadSkills(search);
  };

  const handleInstall = async (skillId: string) => {
    setInstalling(skillId);
    setMessage(null);
    try {
      await apiRequest(`/skills/market/${skillId}/install`, { method: 'POST' });
      setMessage({ type: 'success', text: '✅ 安装成功，可在"本地技能"中查看' });
    } catch (e: any) {
      setMessage({ type: 'error', text: '安装失败: ' + (e.message || '') });
    }
    setInstalling(null);
  };

  const loadReviews = async (skillId: string) => {
    try {
      const data = await apiRequest<{ reviews: any[]; average_rating: number }>(`/skills/market/${skillId}/reviews`);
      setReviews(data.reviews || []);
    } catch {
      setReviews([]);
    }
  };

  const toggleExpand = (skillId: string) => {
    if (expandedSkill === skillId) {
      setExpandedSkill(null);
      setReviews([]);
    } else {
      setExpandedSkill(skillId);
      loadReviews(skillId);
    }
  };

  const submitReview = async (skillId: string) => {
    try {
      await apiRequest(`/skills/market/${skillId}/reviews`, {
        method: 'POST',
        body: JSON.stringify(reviewForm),
      });
      setReviewForm({ rating: 5, comment: '' });
      loadReviews(skillId);
      setMessage({ type: 'success', text: '评论已提交' });
    } catch (e: any) {
      setMessage({ type: 'error', text: '提交失败: ' + (e.message || '') });
    }
  };

  const renderStars = (rating: number) => {
    return '★'.repeat(Math.round(rating)) + '☆'.repeat(5 - Math.round(rating));
  };

  const categories = [...new Set(skills.map(s => s.category))];

  return (
    <div className="max-w-4xl">
      <h3 className="text-[15px] font-semibold mb-1">技能市场</h3>
      <p className="text-[12px] text-muted mb-4">
        浏览社区贡献的技能，一键安装到本地使用。
      </p>

      {message && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-[12px] font-medium flex items-center gap-2 ${
          message.type === 'success' ? 'bg-success/10' : 'bg-danger/10'
        }`}
          style={{
            color: message.type === 'success' ? 'var(--color-mint)' : 'var(--color-danger)',
          }}
        >
          {message.text}
          <button className="ml-auto btn-ghost h-6 w-6 p-0" onClick={() => setMessage(null)}>
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Search */}
      <div className="flex gap-2 mb-4">
        <input
          className="flex-1"
          placeholder="搜索技能名称、描述或作者..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
        <button className="btn-primary h-9 px-4 text-[12px]" onClick={handleSearch}>
          <Search className="w-3.5 h-3.5" />
          搜索
        </button>
      </div>

      {/* Category filter */}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          <button className="px-2.5 py-1 text-[11px] rounded-lg font-medium"
            style={{ background: 'var(--color-tab-active, rgba(101,67,255,0.1))' }}
            onClick={() => loadSkills()}
          >
            全部
          </button>
          {categories.map(cat => (
            <button key={cat} className="px-2.5 py-1 text-[11px] rounded-lg font-medium text-secondary hover:bg-hover"
              onClick={() => loadSkills(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {/* Skill cards */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : skills.length === 0 ? (
        <div className="glass-card p-8 text-center">
          <Globe className="w-10 h-10 text-muted mx-auto mb-3" />
          <p className="text-[13px] text-muted">暂无匹配的技能</p>
          <p className="text-[12px] text-muted mt-1">试试其他关键词</p>
        </div>
      ) : (
        <div className="space-y-3">
          {skills.map((skill) => (
            <div key={skill.id} className="glass-card p-4 hover:bg-hover/20 transition-all">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="text-[14px] font-semibold">{skill.name}</h4>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-tertiary/50 text-muted">
                      v{skill.version}
                    </span>
                  </div>
                  <p className="text-[12px] text-muted line-clamp-2 mb-2">{skill.description}</p>
                  <div className="flex items-center gap-3 text-[11px] text-secondary flex-wrap">
                    <span className="flex items-center gap-1">
                      <Star className="w-3 h-3" style={{ color: 'var(--color-warning)' }} />
                      {skill.rating} ({skill.review_count} 评论)
                    </span>
                    <span>👤 {skill.author}</span>
                    <span>📁 {skill.category}</span>
                    <span>📥 {skill.install_count.toLocaleString()}</span>
                  </div>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {skill.tags.slice(0, 3).map(tag => (
                      <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-tertiary/30 text-muted">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5 flex-shrink-0">
                  <button
                    onClick={() => handleInstall(skill.id)}
                    disabled={installing === skill.id}
                    className="btn-primary h-8 px-3 text-[12px] whitespace-nowrap"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {installing === skill.id ? '安装中...' : '安装'}
                  </button>
                  <button
                    onClick={() => toggleExpand(skill.id)}
                    className="btn-ghost h-7 px-3 text-[11px]"
                  >
                    <MessageSquare className="w-3 h-3" />
                    评论
                  </button>
                </div>
              </div>

              {/* Expandable reviews */}
              {expandedSkill === skill.id && (
                <div className="mt-3 pt-3 border-t border-color/30">
                  {/* Existing reviews */}
                  {reviews.length > 0 && (
                    <div className="mb-3 space-y-2">
                      <p className="text-[11px] font-medium text-secondary">已有 {reviews.length} 条评论</p>
                      {reviews.map((r: any, i: number) => (
                        <div key={i} className="text-[12px] p-2 rounded-lg bg-tertiary/20">
                          <span className="text-warning">{renderStars(r.rating)}</span>
                          <p className="text-muted mt-0.5">{r.comment || '（未填写评论）'}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Review form */}
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-0.5">
                      {[1, 2, 3, 4, 5].map(n => (
                        <button key={n} onClick={() => setReviewForm(p => ({ ...p, rating: n }))}
                          className="text-sm p-0"
                          style={{ color: n <= reviewForm.rating ? 'var(--color-warning)' : 'var(--color-text-muted)' }}
                        >
                          {n <= reviewForm.rating ? '★' : '☆'}
                        </button>
                      ))}
                    </div>
                    <input
                      className="flex-1 text-[12px]"
                      placeholder="写评论（选填）"
                      value={reviewForm.comment}
                      onChange={(e) => setReviewForm(p => ({ ...p, comment: e.target.value }))}
                    />
                    <button className="btn-primary h-7 px-3 text-[11px]" onClick={() => submitReview(skill.id)}>
                      提交
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
