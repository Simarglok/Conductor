import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import { BranchInfoBar } from '../components/BranchInfoBar';
import { TabBar } from '../components/TabBar';
import { CheckBadge } from '../components/CheckBadge';

// ── Types ──────────────────────────────────────────────────────────────────

interface MR {
  id: string;
  title: string;
  source_branch: string;
  target_branch: string;
  status: string;
  author_name: string;
  author_id: string;
  created_at: string;
}

interface Branch {
  name: string;
  last_commit_sha: string;
  ahead_of_main: number;
  behind_main: number;
}

interface Commit {
  sha: string;
  message: string;
  author_name: string;
  author_email: string;
  date: string;
}

interface Check {
  name: string;
  status: string;
  conclusion: string;
  details_url: string;
}

interface Settings {
  self_approve_enabled: boolean;
}

type CheckStatus = 'success' | 'failure' | 'pending';

function mapCheckStatus(conclusion: string): CheckStatus {
  switch (conclusion) {
    case 'success': return 'success';
    case 'failure':
    case 'timed_out':
    case 'cancelled':
      return 'failure';
    default: return 'pending';
  }
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

// ── Create MR Modal ────────────────────────────────────────────────────────

function CreateMRModal({
  slug,
  branches,
  onClose,
  onCreated,
}: {
  slug: string;
  branches: Branch[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [sourceBranch, setSourceBranch] = useState('');
  const [targetBranch, setTargetBranch] = useState('main');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceBranch || !targetBranch || !title.trim()) {
      setError('Source branch, target branch, and title are required.');
      return;
    }
    if (sourceBranch === targetBranch) {
      setError('Source and target branches must be different.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await apiFetch(`/projects/${slug}/git/merge-requests`, {
        method: 'POST',
        body: JSON.stringify({ source_branch: sourceBranch, target_branch: targetBranch, title: title.trim(), description: description.trim() }),
      });
      onCreated();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to create merge request');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-xl w-full max-w-lg mx-4 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Create Merge Request</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Source Branch</label>
            <select
              value={sourceBranch}
              onChange={(e) => setSourceBranch(e.target.value)}
              className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#6366f1]"
            >
              <option value="">Select source branch</option>
              {branches.map((b) => (
                <option key={b.name} value={b.name}>{b.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Target Branch</label>
            <select
              value={targetBranch}
              onChange={(e) => setTargetBranch(e.target.value)}
              className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#6366f1]"
            >
              {branches.map((b) => (
                <option key={b.name} value={b.name}>{b.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Merge request title"
              className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#6366f1] placeholder:text-gray-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description..."
              rows={3}
              className="w-full bg-[#0f1117] border border-[#2a2b36] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#6366f1] placeholder:text-gray-500 resize-none"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="flex gap-2 justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-white rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm bg-[#6366f1] hover:bg-[#4f46e5] text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {submitting ? 'Creating...' : 'Create MR'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Page Component ─────────────────────────────────────────────────────────

export default function GitPage() {
  const { slug } = useParams<{ slug: string }>();
  const [mrs, setMrs] = useState<MR[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [checks, setChecks] = useState<Record<string, Check[]>>({});
  const [settings, setSettings] = useState<Settings>({ self_approve_enabled: false });
  const [tab, setTab] = useState('mr');
  const [showCreateMR, setShowCreateMR] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actioning, setActioning] = useState<string | null>(null);

  // ── Fetch all data ────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    if (!slug) return;
    setLoading(true);
    try {
      const [mrsData, branchesData, commitsData, settingsData] = await Promise.all([
        apiFetch(`/projects/${slug}/git/merge-requests`).catch(() => []),
        apiFetch(`/projects/${slug}/git/branches`).catch(() => []),
        apiFetch(`/projects/${slug}/git/commits?branch=HEAD&limit=50`).catch(() => []),
        apiFetch(`/projects/${slug}/settings`).catch(() => ({ self_approve_enabled: false })),
      ]);
      setMrs(mrsData);
      setBranches(branchesData);
      setCommits(commitsData);
      setSettings(settingsData);

      // Fetch checks for each MR
      const checksMap: Record<string, Check[]> = {};
      await Promise.all(
        mrsData.map(async (mr: MR) => {
          try {
            const c = await apiFetch(`/projects/${slug}/git/merge-requests/${mr.id}/checks`);
            checksMap[mr.id] = c;
          } catch {
            checksMap[mr.id] = [];
          }
        })
      );
      setChecks(checksMap);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Current branch ────────────────────────────────────────────────────

  const currentBranchName = branches.find((b) => b.name === 'main')?.name || branches[0]?.name || 'main';
  const currentBranchData = branches.find((b) => b.name === currentBranchName);

  // ── Actions ───────────────────────────────────────────────────────────

  const handleMerge = async (mrId: string) => {
    setActioning(mrId);
    try {
      await apiFetch(`/projects/${slug}/git/merge-requests/${mrId}/merge`, { method: 'POST' });
      await fetchData();
    } catch {
      // Error handled silently; user can retry
    } finally {
      setActioning(null);
    }
  };

  const handleClose = async (mrId: string) => {
    setActioning(mrId);
    try {
      await apiFetch(`/projects/${slug}/git/merge-requests/${mrId}/close`, { method: 'POST' });
      await fetchData();
    } catch {
      // Error handled silently
    } finally {
      setActioning(null);
    }
  };

  // ── Computed values ───────────────────────────────────────────────────

  const mrCount = mrs.length;
  const branchCount = branches.length;

  const tabs = [
    { id: 'mr', label: `Merge Requests (${mrCount})` },
    { id: 'branches', label: `Branches (${branchCount})` },
    { id: 'commits', label: 'Commits' },
  ];

  // ── Loading state ─────────────────────────────────────────────────────

  if (loading && mrs.length === 0 && branches.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-gray-500">Loading git data...</p>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Branch Info Bar */}
      <BranchInfoBar
        branch={currentBranchName}
        ahead={currentBranchData?.ahead_of_main}
        behind={currentBranchData?.behind_main}
      >
        <div className="flex gap-2">
          <button className="px-3 py-1 text-xs bg-[#6366f1] hover:bg-[#4f46e5] text-white rounded-md transition-colors">
            Push
          </button>
          <button
            onClick={() => setShowCreateMR(true)}
            className="px-3 py-1 text-xs bg-[#6366f1] hover:bg-[#4f46e5] text-white rounded-md transition-colors"
          >
            Create MR
          </button>
        </div>
      </BranchInfoBar>

      {/* Tab Bar */}
      <TabBar tabs={tabs} active={tab} onChange={setTab} />

      {/* ── Merge Requests Tab ─────────────────────────────────────────── */}
      {tab === 'mr' && (
        <div className="space-y-2">
          {mrs.map((mr) => (
            <div
              key={mr.id}
              className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-4"
            >
              {/* Header row: title + status + actions */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-white font-medium">{mr.title}</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    mr.status === 'open'
                      ? 'bg-blue-900 text-blue-400'
                      : mr.status === 'merged'
                        ? 'bg-green-900 text-green-400'
                        : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {mr.status.toUpperCase()}
                </span>
                {/* Merge / Close actions for open MRs */}
                {mr.status === 'open' && (
                  <div className="ml-auto flex gap-2">
                    {!settings.self_approve_enabled && (
                      <button
                        onClick={() => handleMerge(mr.id)}
                        disabled={actioning === mr.id}
                        className="px-3 py-1 text-xs bg-green-700 hover:bg-green-600 text-white rounded-md transition-colors disabled:opacity-50"
                      >
                        {actioning === mr.id ? '...' : 'Merge'}
                      </button>
                    )}
                    <button
                      onClick={() => handleClose(mr.id)}
                      disabled={actioning === mr.id}
                      className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-md transition-colors disabled:opacity-50"
                    >
                      {actioning === mr.id ? '...' : 'Close'}
                    </button>
                  </div>
                )}
              </div>

              {/* Branch arrows + author */}
              <div className="text-xs text-gray-400 mb-2">
                <span className="font-mono text-[#818cf8]">{mr.source_branch}</span>
                <span className="mx-1">→</span>
                <span className="font-mono text-[#818cf8]">{mr.target_branch}</span>
                <span className="mx-1">·</span>
                <span>{mr.author_name}</span>
                <span className="mx-1">·</span>
                <span>{formatDate(mr.created_at)}</span>
              </div>

              {/* Check Badges */}
              {checks[mr.id] && checks[mr.id].length > 0 && (
                <div className="flex gap-3 flex-wrap">
                  {checks[mr.id].map((check) => (
                    <CheckBadge
                      key={check.name}
                      name={check.name}
                      status={mapCheckStatus(check.conclusion)}
                    />
                  ))}
                </div>
              )}
              {checks[mr.id] && checks[mr.id].length === 0 && (
                <p className="text-xs text-gray-500">No checks</p>
              )}
            </div>
          ))}
          {mrs.length === 0 && (
            <p className="text-gray-500 text-sm py-4">No merge requests</p>
          )}
        </div>
      )}

      {/* ── Branches Tab ────────────────────────────────────────────────── */}
      {tab === 'branches' && (
        <div className="space-y-1">
          {branches.length === 0 ? (
            <p className="text-gray-500 text-sm py-4">No branches</p>
          ) : (
            branches.map((branch) => (
              <div
                key={branch.name}
                className="flex items-center gap-3 bg-[#1a1b23] border border-[#2a2b36] rounded-lg px-4 py-3"
              >
                <span className="font-mono text-[#818cf8] text-sm flex-1">{branch.name}</span>
                <span className="font-mono text-xs text-gray-500">{shortSha(branch.last_commit_sha)}</span>
                {branch.ahead_of_main > 0 && (
                  <span className="text-green-400 text-xs">↑ {branch.ahead_of_main}</span>
                )}
                {branch.behind_main > 0 && (
                  <span className="text-yellow-400 text-xs">↓ {branch.behind_main}</span>
                )}
                {branch.ahead_of_main === 0 && branch.behind_main === 0 && (
                  <span className="text-gray-500 text-xs">up to date</span>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Commits Tab ─────────────────────────────────────────────────── */}
      {tab === 'commits' && (
        <div className="space-y-1">
          {commits.length === 0 ? (
            <p className="text-gray-500 text-sm py-4">No commits</p>
          ) : (
            commits.map((commit) => (
              <div
                key={commit.sha}
                className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg px-4 py-3"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs text-[#818cf8]">{shortSha(commit.sha)}</span>
                  <span className="text-white text-sm">{commit.message}</span>
                </div>
                <div className="text-xs text-gray-400">
                  <span>{commit.author_name}</span>
                  <span className="mx-1">·</span>
                  <span>{formatDate(commit.date)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Create MR Modal ─────────────────────────────────────────────── */}
      {showCreateMR && (
        <CreateMRModal
          slug={slug!}
          branches={branches}
          onClose={() => setShowCreateMR(false)}
          onCreated={fetchData}
        />
      )}
    </div>
  );
}
