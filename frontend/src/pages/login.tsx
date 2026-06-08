import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { authApi } from '@/lib/api';

export function LoginPage() {
  const navigate = useNavigate();
  const auth = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password) {
      setError('请填写用户名和密码');
      return;
    }

    setLoading(true);
    try {
      const data = await authApi.login({ username: username.trim(), password });
      auth.login(data.token, data.user);
      navigate('/chat', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--color-bg-deep)' }}>
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
            style={{
              background: 'linear-gradient(135deg, rgba(255,107,107,0.15), rgba(0,240,255,0.1))',
              border: '1px solid rgba(255,107,107,0.15)',
            }}
          >
            <Sparkles className="w-7 h-7" style={{ color: 'var(--color-accent)' }} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-primary">欢迎回来</h1>
          <p className="text-[13px] mt-1 text-secondary">登录 EvoGen 继续对话</p>
        </div>

        {/* Form card */}
        <div className="card space-y-4">
          {error && (
            <div
              className="text-[12px] px-3 py-2 rounded-lg"
              style={{
                background: 'rgba(220,53,69,0.08)',
                border: '1px solid rgba(220,53,69,0.2)',
                color: 'var(--color-danger)',
              }}
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                className="block text-[12px] font-medium mb-1.5"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                className="w-full"
                autoComplete="username"
                autoFocus
              />
            </div>

            <div>
              <label
                className="block text-[12px] font-medium mb-1.5"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                密码
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入密码"
                  className="w-full pr-10"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-hover transition-colors"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  {showPassword ? <EyeOff style={{ width: 16, height: 16 }} /> : <Eye style={{ width: 16, height: 16 }} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center h-10 text-[14px]"
            >
              {loading ? '登录中…' : '登录'}
            </button>
          </form>
        </div>

        {/* Footer link */}
        <p className="text-center mt-5 text-[12px] text-secondary">
          没有账号？{' '}
          <Link to="/register" className="font-medium hover:underline" style={{ color: 'var(--color-accent)' }}>
            去注册
          </Link>
        </p>
      </div>
    </div>
  );
}
