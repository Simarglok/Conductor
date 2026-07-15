import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';

interface DAG { dag_id: string; description: string | null; is_paused: boolean; }

export default function PipelinePage() {
  const { slug } = useParams();
  const [dags, setDags] = useState<DAG[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDag, setSelectedDag] = useState<string | null>(null);

  useEffect(() => {
    apiFetch(`/projects/${slug}/airflow/dags`).then(setDags).catch(() => setDags([])).finally(() => setLoading(false));
  }, [slug]);

  return (
    <div>
      <h1 className="text-xl font-bold text-white mb-4">Production Pipeline</h1>
      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          { label: 'Active DAGs', value: dags.length, color: 'text-green-500' },
          { label: 'Paused', value: dags.filter(d => d.is_paused).length, color: 'text-yellow-500' },
        ].map(s => (
          <div key={s.label} className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-3">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-gray-400 mt-1">{s.label}</div>
          </div>
        ))}
      </div>
      <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg overflow-hidden">
        {loading && <div className="p-4 text-gray-400 text-sm">Loading DAGs...</div>}
        {!loading && dags.length === 0 && (
          <div className="p-8 text-center text-gray-500">
            <p>No DAGs found</p>
            <p className="text-xs mt-2">Provision Airflow for this project first</p>
          </div>
        )}
        {dags.map(dag => (
          <div key={dag.dag_id} onClick={() => setSelectedDag(dag.dag_id)}
            className="flex items-center px-4 py-3 border-b border-[#2a2b36] hover:bg-[#22232d] cursor-pointer">
            <span className="flex-1 text-sm text-white font-medium">{dag.dag_id}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${dag.is_paused ? 'bg-yellow-900 text-yellow-400' : 'bg-green-900 text-green-400'}`}>
              {dag.is_paused ? 'PAUSED' : 'ACTIVE'}
            </span>
          </div>
        ))}
      </div>
      {selectedDag && (
        <div className="mt-4 bg-[#1a1b23] border border-[#2a2b36] rounded-lg overflow-hidden" style={{ height: '400px' }}>
          <iframe
            src={`/api/v1/projects/${slug}/airflow-iframe/dags/${selectedDag}`}
            className="w-full h-full border-none"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      )}
    </div>
  );
}