import { useState } from 'react';
import { useAuth } from '../lib/auth';

export default function RegisterPage() {
  const { register } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await register(email, password, name); window.location.href = '/projects'; }
    catch (err: any) { setError(err.message); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f1117]">
      <form onSubmit={handleSubmit} className="bg-[#1a1b23] border border-[#2a2b36] rounded-xl p-8 w-96">
        <h2 className="text-xl font-bold text-white mb-1">Create Account</h2>
        <p className="text-sm text-gray-400 mb-6">Join Conductor</p>
        {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
        <input className="w-full p-2.5 mb-3 bg-[#22232d] border border-[#2a2b36] rounded text-white text-sm" placeholder="Display Name" value={name} onChange={e => setName(e.target.value)} />
        <input className="w-full p-2.5 mb-3 bg-[#22232d] border border-[#2a2b36] rounded text-white text-sm" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
        <input className="w-full p-2.5 mb-4 bg-[#22232d] border border-[#2a2b36] rounded text-white text-sm" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} />
        <button className="w-full py-2.5 bg-[#6366f1] text-white rounded font-medium">Register</button>
        <p className="mt-4 text-xs text-gray-500 text-center">Already have an account? <a href="/login" className="text-[#818cf8]">Sign In</a></p>
      </form>
    </div>
  );
}