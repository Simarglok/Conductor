import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';

export default function SettingsPage() {
  const { slug } = useParams();
  const [gitConfig, setGitConfig] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);

  useEffect(() => {
    apiFetch(`/projects/${slug}/git`).then(setGitConfig).catch(() => {});
    apiFetch(`/projects/${slug}/settings`).then(setSettings).catch(() => {});
  }, [slug]);

  const toggleSelfApprove = async () => {
    const newVal = !settings?.self_approve_enabled;
    await apiFetch(`/projects/${slug}/settings`, {
      method: 'PATCH', body: JSON.stringify({ self_approve_enabled: newVal }),
    });
    setSettings((s: any) => ({ ...s, self_approve_enabled: newVal }));
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-white mb-4">Project Settings</h1>
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
          <h3 className="text-white font-medium mb-3">Git Repository</h3>
          {gitConfig ? (
            <>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">URL</span><span className="text-[#818cf8] font-mono text-xs">{gitConfig.repo_url}</span></div>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">Branch</span><span className="text-gray-300">{gitConfig.default_branch}</span></div>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">dbt Path</span><span className="text-gray-300">{gitConfig.dbt_path}</span></div>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">DAGs Path</span><span className="text-gray-300">{gitConfig.dags_path}</span></div>
            </>
          ) : <p className="text-gray-500 text-sm">Not configured</p>}
        </div>
        <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
          <h3 className="text-white font-medium mb-3">Features</h3>
          <label className="flex items-center gap-3 text-sm text-gray-300">
            <input type="checkbox" checked={settings?.self_approve_enabled || false} onChange={toggleSelfApprove}
              className="w-4 h-4 rounded border-gray-500 bg-gray-800 accent-[#6366f1]" />
            Allow self-approve
          </label>
          <p className="text-xs text-gray-500 mt-1">Authors can merge their own merge requests</p>
        </div>
      </div>
    </div>
  );
}