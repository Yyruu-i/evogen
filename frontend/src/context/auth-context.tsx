import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';

/* ── Types ────────────────────────────────────────────────────── */
interface User {
  id: string;
  username: string;
  email: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (token: string, user: User) => void;
  logout: () => void;
}

/* ── Storage keys ─────────────────────────────────────────────── */
const TOKEN_KEY = 'evogen-auth-token';
const USER_KEY = 'evogen-auth-user';

/* ── Helpers ──────────────────────────────────────────────────── */
function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

function storeAuth(token: string, user: User) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // localStorage may be unavailable
  }
}

function clearAuth() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    // localStorage may be unavailable
  }
}

/* ── Context ──────────────────────────────────────────────────── */
const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const token = getStoredToken();
    const user = getStoredUser();
    return {
      token,
      user,
      isAuthenticated: token !== null && user !== null,
    };
  });

  const login = useCallback((token: string, user: User) => {
    storeAuth(token, user);
    setState({ token, user, isAuthenticated: true });
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setState({ token: null, user: null, isAuthenticated: false });
  }, []);

  // Sync with other tabs (optional)
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === TOKEN_KEY) {
        const token = getStoredToken();
        const user = getStoredUser();
        setState({ token, user, isAuthenticated: token !== null && user !== null });
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
