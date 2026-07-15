import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';

export default function DevPage() {
  const { slug } = useParams();
  const [iframeUrl, setIframeUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        await apiFetch(`/projects/${slug}/codeserver/setup-workspace`);
        const data = await apiFetch(`/projects/${slug}/codeserver/token`);
        setIframeUrl(data.iframe_url);
      } catch (err: any) { setError(err.message); }
      finally { setLoading(false); }
    })();
  }, [slug]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 mb-3">
        <h1 className="text-lg font-bold text-white">Development</h1>
        {iframeUrl && (
          <a href={iframeUrl} target="_blank" className="text-xs text-[#818cf8] hover:underline ml-auto">Open in new tab ↗</a>
        )}
      </div>
      {loading && <div className="flex-1 flex items-center justify-center text-gray-400">Setting up workspace...</div>}
      {error && <div className="flex-1 flex items-center justify-center text-red-400">{error}</div>}
      {iframeUrl && (
        <div className="flex-1 bg-[#1a1b23] border border-[#2a2b36] rounded-lg overflow-hidden">
          <iframe src={iframeUrl} className="w-full h-full border-none"
            sandbox="allow-scripts allow-same-origin"
            allow="clipboard-read; clipboard-write"
          />
        </div>
      )}
    </div>
  );
}