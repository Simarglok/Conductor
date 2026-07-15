import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';

interface MR {
  id: string; title: string; source_branch: string; target_branch: string;
  status: string; author_name: string; created_at: string;
}

export default function GitPage() {
  const { slug } = useParams();
  const [mrs, setMrs] = useState<MR[]>([]);
  const [tab, setTab] = useState('mr');

  useEffect(() => {
    apiFetch(`/projects/${slug}/git/merge-requests`).then(setMrs).catch(() => setMrs([]));
  }, [slug]);

  return (
    <div>
      <h1 className="text-xl font-bold text-white mb-4">Git / Branches</h1>
      <div className="flex gap-0 border-b border-[#2a2b36] mb-4">
        {['mr', 'branches', 'commits'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm border-b-2 -mb-px ${tab === t ? 'text-white border-[#6366f1]' : 'text-gray-400 border-transparent'}`}>
            {t === 'mr' ? 'Merge Requests' : t === 'branches' ? 'Branches' : 'Commits'}
          </button>
        ))}
      </div>
      {tab === 'mr' && (
        <div className="space-y-2">
          {mrs.map(mr => (
            <div key={mr.id} className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
              <div className="flex items-center gap-2">
                <span className="text-white font-medium">{mr.title}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  mr.status === 'open' ? 'bg-blue-900 text-blue-400' :
                  mr.status === 'merged' ? 'bg-green-900 text-green-400' : 'bg-gray-800 text-gray-400'
                }`}>{mr.status.toUpperCase()}</span>
              </div>
              <div className="text-xs text-gray-400 mt-2">
                {mr.source_branch} → {mr.target_branch} · by {mr.author_name}
              </div>
            </div>
          ))}
          {mrs.length === 0 && <p className="text-gray-500 text-sm">No merge requests</p>}
        </div>
      )}
      {tab === 'branches' && <p className="text-gray-500 text-sm">Branch list loading...</p>}
      {tab === 'commits' && <p className="text-gray-500 text-sm">Commit history loading...</p>}
    </div>
  );
}