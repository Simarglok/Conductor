import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../lib/api';

interface Project {
  id: string; name: string; slug: string; description: string | null;
  member_count: number; created_at: string;
}

export default function ProjectListPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    apiFetch('/projects').then(setProjects).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 p-8">Loading projects...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Your Projects</h1>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {projects.map(p => (
          <div key={p.id} onClick={() => navigate(`/projects/${p.slug}/pipeline`)}
            className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4 cursor-pointer hover:border-[#6366f1] transition-colors">
            <h3 className="text-white font-semibold">{p.name}</h3>
            <p className="text-xs text-gray-400 mt-1">{p.description || 'No description'}</p>
            <p className="text-xs text-gray-500 mt-2">{p.member_count} members</p>
          </div>
        ))}
      </div>
    </div>
  );
}