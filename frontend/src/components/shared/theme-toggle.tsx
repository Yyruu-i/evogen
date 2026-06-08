import { useState, useEffect } from 'react';
import { Sun, Moon } from 'lucide-react';

const STORAGE_KEY = 'evogen-theme';

export function getStoredTheme(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

export function applyTheme(theme: 'light' | 'dark') {
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
  localStorage.setItem(STORAGE_KEY, theme);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const stored = getStoredTheme();
    if (stored === 'dark' || stored === 'light') return stored;
    // DEFAULT: light mode
    return 'light';
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = () => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));

  return (
    <button className="theme-toggle" onClick={toggle} title={theme === 'light' ? '切换暗色模式' : '切换浅色模式'}>
      {theme === 'light' ? <Sun style={{ width: 16, height: 16 }} /> : <Moon style={{ width: 16, height: 16 }} />}
    </button>
  );
}
