const API = '/api/v1';

export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem('conductor_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const r = await fetch(`${API}${path}`, { ...options, headers });

  if (r.status === 401) {
    localStorage.removeItem('conductor_token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  if (r.status === 204) return null;
  return r.json();
}