import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import { BranchInfoBar } from '../components/BranchInfoBar';

interface WorkspaceInfo {
  branch: string;
  ahead: number;
  behind: number;
  files: string[];
}

function JwtCountdown({ expiresIn, onRefresh }: { expiresIn: number; onRefresh: () => void }) {
  const [remaining, setRemaining] = useState(expiresIn);

  useEffect(() => {
    setRemaining(expiresIn);
  }, [expiresIn]);

  useEffect(() => {
    if (remaining <= 0) return;
    const timer = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [remaining <= 0]);

  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const color =
    remaining > 60 ? 'text-green-400' : remaining > 0 ? 'text-yellow-400' : 'text-red-400';

  if (remaining <= 0) {
    return (
      <button onClick={onRefresh} className="text-xs text-red-400 hover:underline">
        ● Expired — refresh
      </button>
    );
  }

  return (
    <span className={`text-xs ${color}`}>
      ● {mins}:{secs.toString().padStart(2, '0')} remaining
    </span>
  );
}

export default function DevPage() {
  const { slug } = useParams();
  const [iframeUrl, setIframeUrl] = useState('');
  const [expiresIn, setExpiresIn] = useState(0);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadWorkspace = useCallback(async () => {
    try {
      await apiFetch(`/projects/${slug}/codeserver/setup-workspace`, { method: 'POST' });
      const [tokenData, wsData] = await Promise.all([
        apiFetch(`/projects/${slug}/codeserver/token`, { method: 'POST' }),
        apiFetch(`/projects/${slug}/codeserver/workspace-info`).catch(() => null),
      ]);
      setIframeUrl(tokenData.iframe_url);
      setExpiresIn(tokenData.expires_in || 900);
      if (wsData) setWorkspace(wsData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const handleRefresh = () => {
    setLoading(true);
    setError('');
    loadWorkspace();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <h1 className="text-lg font-bold text-white">Development</h1>
        <JwtCountdown expiresIn={expiresIn} onRefresh={handleRefresh} />
      </div>

      {workspace && (
        <BranchInfoBar
          branch={workspace.branch}
          ahead={workspace.ahead}
          behind={workspace.behind}
        >
          <button
            onClick={handleRefresh}
            className="px-2 py-1 text-xs border border-[#2a2b36] text-gray-300 rounded hover:text-white hover:border-[#6366f1] transition-colors"
          >
            Sync
          </button>
          {iframeUrl && (
            <button
              onClick={() => window.open(iframeUrl, '_blank')}
              className="px-3 py-1 text-xs bg-[#6366f1] text-white rounded hover:bg-[#4f46e5] transition-colors"
            >
              Open in new tab ↗
            </button>
          )}
        </BranchInfoBar>
      )}

      {workspace?.files && workspace.files.length > 0 && (
        <div className="flex gap-4 text-xs text-gray-500 mb-2">
          {workspace.files.map((f) => (
            <span key={f}>📁 {f}</span>
          ))}
        </div>
      )}

      {loading && (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          Setting up workspace...
        </div>
      )}
      {error && (
        <div className="flex-1 flex items-center justify-center text-red-400">{error}</div>
      )}
      {iframeUrl && (
        <div className="flex-1 bg-[#1a1b23] border border-[#2a2b36] rounded-lg overflow-hidden">
          <iframe
            src={iframeUrl}
            className="w-full h-full border-none"
            sandbox="allow-scripts allow-same-origin"
            allow="clipboard-read; clipboard-write"
          />
        </div>
      )}
    </div>
  );
}