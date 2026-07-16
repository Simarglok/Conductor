import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import { RoleBadge } from '../components/RoleBadge';

interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  member_count: number;
  role: string | null;
  created_at: string;
}

function CreateProjectModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const slug = name
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      await apiFetch('/projects', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), slug, description: description.trim() || null }),
      });
      onCreated();
      onClose();
      setName('');
      setDescription('');
    } catch (err: any) {
      setError(err.message || 'Failed to create project');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold text-white mb-4">New Project</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Name</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
              placeholder="My Project"
              required
            />
            {slug && (
              <p className="text-xs text-gray-500 mt-1">
                Slug: <span className="font-mono text-gray-400">{slug}</span>
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none resize-none"
              rows={3}
              placeholder="Optional description..."
            />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="px-3 py-1.5 bg-[#6366f1] text-white text-xs rounded-md hover:bg-[#4f46e5] disabled:opacity-50"
            >
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ProjectListPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const navigate = useNavigate();

  const fetchProjects = () => {
    apiFetch('/projects')
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  if (loading) return <div className="text-gray-400 p-8">Loading projects...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Your Projects</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-1.5 bg-[#6366f1] text-white text-xs rounded-md hover:bg-[#4f46e5] transition-colors"
        >
          + New Project
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {projects.map((p) => (
          <div
            key={p.id}
            onClick={() => navigate(`/projects/${p.slug}/pipeline`)}
            className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4 cursor-pointer hover:border-[#6366f1] transition-colors"
          >
            <h3 className="text-white font-semibold">{p.name}</h3>
            <p className="text-xs text-gray-400 mt-1">
              {p.description || 'No description'}
            </p>
            <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
              <span>{p.member_count} members</span>
              {p.role && <RoleBadge role={p.role} />}
            </div>
          </div>
        ))}
      </div>

      {projects.length === 0 && (
        <p className="text-gray-500 text-sm text-center mt-12">
          No projects yet. Create one to get started.
        </p>
      )}

      <CreateProjectModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={fetchProjects}
      />
    </div>
  );
}