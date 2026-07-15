import { useState } from 'react';
import { useAuth } from '../lib/auth';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try { await login(email, password); window.location.href = '/projects'; }
    catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f1117]">
      <form onSubmit={handleSubmit} className="bg-[#1a1b23] border border-[#2a2b36] rounded-xl p-8 w-96">
        <h2 className="text-xl font-bold text-white mb-1">Conductor</h2>
        <p className="text-sm text-gray-400 mb-6">Data Transformation Platform</p>
        {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
        <input className="w-full p-2.5 mb-3 bg-[#22232d] border border-[#2a2b36] rounded text-white text-sm" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
        <input className="w-full p-2.5 mb-4 bg-[#22232d] border border-[#2a2b36] rounded text-white text-sm" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} />
        <button className="w-full py-2.5 bg-[#6366f1] text-white rounded font-medium hover:bg-[#4f46e5]" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
        <p className="mt-4 text-xs text-gray-500 text-center">
          Don't have an account? <a href="/register" className="text-[#818cf8]">Register</a>
        </p>
      </form>
    </div>
  );
}