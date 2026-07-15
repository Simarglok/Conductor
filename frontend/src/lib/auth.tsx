import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface User {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  projects: Array<{ project_id: string; slug: string; name: string; role: string }>;
}

interface AuthState {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, display_name: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

const API = '/api/v1';

function storeToken(token: string) {
  localStorage.setItem('conductor_token', token);
}

function getToken(): string | null {
  return localStorage.getItem('conductor_token');
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(getToken());

  useEffect(() => {
    if (token) {
      fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.ok ? r.json() : null)
        .then(u => { if (u) setUser(u); else { setToken(null); localStorage.removeItem('conductor_token'); } })
        .catch(() => { setToken(null); localStorage.removeItem('conductor_token'); });
    }
  }, [token]);

  const login = async (email: string, password: string) => {
    const r = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) throw new Error('Login failed');
    const data = await r.json();
    storeToken(data.access_token);
    setToken(data.access_token);
    const me = await fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${data.access_token}` } });
    setUser(await me.json());
  };

  const register = async (email: string, password: string, display_name: string) => {
    const r = await fetch(`${API}/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, display_name }),
    });
    if (!r.ok) throw new Error('Registration failed');
    const data = await r.json();
    storeToken(data.access_token);
    setToken(data.access_token);
    const me = await fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${data.access_token}` } });
    setUser(await me.json());
  };

  const logout = () => {
    localStorage.removeItem('conductor_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}