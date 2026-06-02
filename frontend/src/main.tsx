import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { getStoredTheme, applyTheme } from '@/components/shared/theme-toggle';
import './index.css';
import App from './App';

// Apply stored theme before React renders to prevent flash
// DEFAULT: dark mode (when no localStorage record)
const stored = getStoredTheme();
if (stored === 'dark' || stored === 'light') {
  applyTheme(stored);
} else {
  // No stored preference → default to dark
  document.documentElement.classList.add('dark');
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
