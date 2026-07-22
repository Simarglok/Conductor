import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import { TabBar } from '../components/TabBar';
import { RoleBadge } from '../components/RoleBadge';

const ROLE_OPTIONS = ['super_admin', 'project_admin', 'maintainer', 'developer', 'viewer'];

export default function SettingsPage() {
  const { slug } = useParams();
  const [activeTab, setActiveTab] = useState('git');
  const [gitConfig, setGitConfig] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);

  // Git edit mode
  const [editingGit, setEditingGit] = useState(false);
  const [formGit, setFormGit] = useState({
    repo_url: '',
    auth_type: 'https',
    token: '',
    default_branch: 'main',
    dbt_path: '',
    dags_path: '',
  });

  // Environment add form
  const [formEnv, setFormEnv] = useState({ name: '', branch_name: '', is_protected: false });

  // Member invite form
  const [formMember, setFormMember] = useState({ email: '', role_name: 'developer' });

  useEffect(() => {
    apiFetch(`/projects/${slug}/git`).then(setGitConfig).catch(() => {});
    apiFetch(`/projects/${slug}/settings`).then(setSettings).catch(() => {});
    apiFetch(`/projects/${slug}/members`).then(setMembers).catch(() => {});
    apiFetch(`/projects/${slug}/environments`).then(setEnvironments).catch(() => {});
  }, [slug]);

  // Sync git form when gitConfig loads
  useEffect(() => {
    if (gitConfig) {
      setFormGit({
        repo_url: gitConfig.repo_url || '',
        auth_type: gitConfig.auth_type || 'https',
        token: '',
        default_branch: gitConfig.default_branch || 'main',
        dbt_path: gitConfig.dbt_path || '',
        dags_path: gitConfig.dags_path || '',
      });
    }
  }, [gitConfig]);

  const toggleSelfApprove = async () => {
    const newVal = !settings?.self_approve_enabled;
    await apiFetch(`/projects/${slug}/settings`, {
      method: 'PATCH', body: JSON.stringify({ self_approve_enabled: newVal }),
    });
    setSettings((s: any) => ({ ...s, self_approve_enabled: newVal }));
  };

  // Git save
  const handleGitSave = async () => {
    const payload = { ...formGit, token: formGit.token || undefined };
    const savedConfig = await apiFetch(`/projects/${slug}/git`, {
      method: 'PUT', body: JSON.stringify(payload),
    });
    setGitConfig(savedConfig);
    setEditingGit(false);
  };

  // Environment add
  const handleEnvAdd = async () => {
    const newEnv = await apiFetch(`/projects/${slug}/environments`, {
      method: 'POST', body: JSON.stringify(formEnv),
    });
    setEnvironments((prev: any[]) => [...prev, newEnv]);
    setFormEnv({ name: '', branch_name: '', is_protected: false });
  };

  // Environment delete
  const handleEnvDelete = async (envId: string) => {
    await apiFetch(`/projects/${slug}/environments/${envId}`, { method: 'DELETE' });
    setEnvironments((prev: any[]) => prev.filter((e: any) => e.id !== envId));
  };

  // Member invite
  const handleMemberInvite = async () => {
    const newMember = await apiFetch(`/projects/${slug}/members`, {
      method: 'POST', body: JSON.stringify(formMember),
    });
    setMembers((prev: any[]) => [...prev, newMember]);
    setFormMember({ email: '', role_name: 'developer' });
  };

  // Member remove
  const handleMemberRemove = async (userId: string) => {
    await apiFetch(`/projects/${slug}/members/${userId}`, { method: 'DELETE' });
    setMembers((prev: any[]) => prev.filter((m: any) => m.user_id !== userId));
  };

  const tabs = [
    { id: 'git', label: 'Git & Repository' },
    { id: 'environments', label: 'Environments' },
    { id: 'members', label: `Members (${members.length})` },
    { id: 'features', label: 'Feature Toggles' },
  ];

  return (
    <div>
      <h1 className="text-xl font-bold text-white mb-4">Project Settings</h1>
      <TabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

      {/* Tab 1: Git & Repository */}
      {activeTab === 'git' && (
        <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-white font-medium">Git Repository</h3>
            {!editingGit && (
              <button
                onClick={() => setEditingGit(true)}
                className="text-sm text-[#6366f1] hover:text-[#818cf8] cursor-pointer"
              >
                Edit Config
              </button>
            )}
          </div>
          {gitConfig && !editingGit ? (
            <>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">URL</span><span className="text-[#818cf8] font-mono text-xs">{gitConfig.repo_url}</span></div>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">Auth Type</span><span className="text-gray-300">{gitConfig.auth_type}</span></div>
              {gitConfig.auth_type === 'token' && (
                <div className="flex justify-between py-1 text-sm">
                  <span className="text-gray-400">Access Token</span>
                  <span className="text-gray-300">{gitConfig.has_token || gitConfig.has_credentials ? 'Configured' : 'Not configured'}</span>
                </div>
              )}
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">Branch</span><span className="text-gray-300">{gitConfig.default_branch}</span></div>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">dbt Path</span><span className="text-gray-300">{gitConfig.dbt_path}</span></div>
              <div className="flex justify-between py-1 text-sm"><span className="text-gray-400">DAGs Path</span><span className="text-gray-300">{gitConfig.dags_path}</span></div>
            </>
          ) : editingGit ? (
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Repository URL</label>
                <input
                  type="text"
                  value={formGit.repo_url}
                  onChange={(e) => setFormGit({ ...formGit, repo_url: e.target.value })}
                  className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Auth Type</label>
                <select
                  value={formGit.auth_type}
                  onChange={(e) => setFormGit({ ...formGit, auth_type: e.target.value })}
                  className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                >
                  <option value="https">HTTPS</option>
                  <option value="ssh">SSH</option>
                  <option value="token">Token</option>
                </select>
              </div>
              {formGit.auth_type === 'token' && (
                <div>
                  <label className="block text-sm text-gray-400 mb-1" htmlFor="git-access-token">Access Token</label>
                  <input
                    id="git-access-token"
                    type="password"
                    autoComplete="new-password"
                    value={formGit.token}
                    onChange={(e) => setFormGit({ ...formGit, token: e.target.value })}
                    placeholder={gitConfig?.has_token ? 'Leave blank to keep the saved token' : 'Personal access token'}
                    className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                  />
                  <p className="text-xs text-gray-500 mt-1">Stored encrypted and never returned by the API.</p>
                </div>
              )}
              <div>
                <label className="block text-sm text-gray-400 mb-1">Default Branch</label>
                <input
                  type="text"
                  value={formGit.default_branch}
                  onChange={(e) => setFormGit({ ...formGit, default_branch: e.target.value })}
                  className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">dbt Path</label>
                <input
                  type="text"
                  value={formGit.dbt_path}
                  onChange={(e) => setFormGit({ ...formGit, dbt_path: e.target.value })}
                  className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">DAGs Path</label>
                <input
                  type="text"
                  value={formGit.dags_path}
                  onChange={(e) => setFormGit({ ...formGit, dags_path: e.target.value })}
                  className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button
                  onClick={handleGitSave}
                  disabled={formGit.auth_type === 'token' && !formGit.token && !gitConfig?.has_token}
                  className="px-4 py-1.5 text-sm rounded-md bg-[#6366f1] text-white hover:bg-[#4f46e5] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  Save
                </button>
                <button
                  onClick={() => setEditingGit(false)}
                  className="px-4 py-1.5 text-sm rounded-md border border-[#2a2b36] text-gray-400 hover:text-white cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Not configured</p>
          )}
        </div>
      )}

      {/* Tab 2: Environments */}
      {activeTab === 'environments' && (
        <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
          <h3 className="text-white font-medium mb-3">Environments</h3>

          {environments.length > 0 ? (
            <div className="space-y-2 mb-4">
              {environments.map((env: any) => (
                <div
                  key={env.id}
                  className="flex items-center justify-between px-3 py-2 rounded-md bg-[#0f1117] border border-[#2a2b36]"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-white text-sm font-medium">{env.name}</span>
                    <span className="text-gray-400 text-xs font-mono">{env.branch_name}</span>
                    {env.is_protected && (
                      <span className="text-yellow-500 text-xs" title="Protected">🔒</span>
                    )}
                  </div>
                  <button
                    onClick={() => handleEnvDelete(env.id)}
                    className="text-gray-500 hover:text-red-400 cursor-pointer text-sm"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm mb-4">No environments configured</p>
          )}

          <div className="border-t border-[#2a2b36] pt-3">
            <h4 className="text-sm text-gray-400 mb-2">Add Environment</h4>
            <div className="flex gap-2 items-end flex-wrap">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Name</label>
                <input
                  type="text"
                  value={formEnv.name}
                  onChange={(e) => setFormEnv({ ...formEnv, name: e.target.value })}
                  placeholder="production"
                  className="bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none w-32"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Branch</label>
                <input
                  type="text"
                  value={formEnv.branch_name}
                  onChange={(e) => setFormEnv({ ...formEnv, branch_name: e.target.value })}
                  placeholder="main"
                  className="bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none w-32"
                />
              </div>
              <div className="flex items-center gap-1.5 pb-2">
                <input
                  type="checkbox"
                  checked={formEnv.is_protected}
                  onChange={(e) => setFormEnv({ ...formEnv, is_protected: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-500 bg-gray-800 accent-[#6366f1]"
                />
                <label className="text-xs text-gray-400">Protected</label>
              </div>
              <button
                onClick={handleEnvAdd}
                disabled={!formEnv.name || !formEnv.branch_name}
                className="px-4 py-2 text-sm rounded-md bg-[#6366f1] text-white hover:bg-[#4f46e5] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Members */}
      {activeTab === 'members' && (
        <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
          <h3 className="text-white font-medium mb-3">Members</h3>

          {members.length > 0 ? (
            <div className="space-y-2 mb-4">
              {members.map((member: any) => (
                <div
                  key={member.user_id}
                  className="flex items-center justify-between px-3 py-2 rounded-md bg-[#0f1117] border border-[#2a2b36]"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-white text-sm">{member.email}</span>
                    <RoleBadge role={member.role_name} />
                  </div>
                  <button
                    onClick={() => handleMemberRemove(member.user_id)}
                    className="text-gray-500 hover:text-red-400 cursor-pointer text-sm"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm mb-4">No members</p>
          )}

          <div className="border-t border-[#2a2b36] pt-3">
            <h4 className="text-sm text-gray-400 mb-2">Invite Member</h4>
            <div className="flex gap-2 items-end flex-wrap">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Email</label>
                <input
                  type="email"
                  value={formMember.email}
                  onChange={(e) => setFormMember({ ...formMember, email: e.target.value })}
                  placeholder="user@example.com"
                  className="bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none w-48"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Role</label>
                <select
                  value={formMember.role_name}
                  onChange={(e) => setFormMember({ ...formMember, role_name: e.target.value })}
                  className="bg-[#0f1117] border border-[#2a2b36] rounded-md px-3 py-2 text-white text-sm focus:border-[#6366f1] outline-none"
                >
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>{role.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleMemberInvite}
                disabled={!formMember.email}
                className="px-4 py-2 text-sm rounded-md bg-[#6366f1] text-white hover:bg-[#4f46e5] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Invite
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Feature Toggles */}
      {activeTab === 'features' && (
        <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4">
          <h3 className="text-white font-medium mb-3">Features</h3>
          <label className="flex items-center gap-3 text-sm text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={settings?.self_approve_enabled || false}
              onChange={toggleSelfApprove}
              className="w-4 h-4 rounded border-gray-500 bg-gray-800 accent-[#6366f1] cursor-pointer"
            />
            Allow self-approve
          </label>
          <p className="text-xs text-gray-500 mt-1">Authors can merge their own merge requests</p>
          <div className="border-t border-[#2a2b36] mt-4 pt-3">
            <p className="text-xs text-gray-500 italic">More feature toggles coming soon</p>
          </div>
        </div>
      )}
    </div>
  );
}
