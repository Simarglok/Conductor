import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';

export default function AdminPage() {
  const [users, setUsers] = useState<any[]>([]);

  useEffect(() => {
    apiFetch('/admin/users').then(setUsers).catch(() => setUsers([]));
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold text-white mb-4">Admin Panel</h1>
      <h2 className="text-white font-medium mb-2">Users ({users.length})</h2>
      <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[#2a2b36]">
            <th className="text-left p-3 text-gray-400 font-medium">User</th>
            <th className="text-left p-3 text-gray-400 font-medium">Role</th>
            <th className="text-left p-3 text-gray-400 font-medium">Status</th>
          </tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[#2a2b36]">
                <td className="p-3 text-white">{u.email}</td>
                <td className="p-3"><span className={`text-xs px-2 py-0.5 rounded-full ${u.is_admin ? 'bg-indigo-900 text-indigo-300' : 'bg-gray-800 text-gray-300'}`}>{u.is_admin ? 'Super Admin' : 'User'}</span></td>
                <td className="p-3"><span className={u.is_active ? 'text-green-400' : 'text-red-400'}>{u.is_active ? 'Active' : 'Inactive'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}