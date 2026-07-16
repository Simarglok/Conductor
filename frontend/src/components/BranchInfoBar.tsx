import type { ReactNode } from 'react';

interface BranchInfoBarProps {
  branch: string;
  ahead?: number;
  behind?: number;
  children?: ReactNode;
}

export function BranchInfoBar({ branch, ahead, behind, children }: BranchInfoBarProps) {
  return (
    <div className="flex items-center gap-2 bg-[#1a1b23] border border-[#2a2b36] rounded-lg px-4 py-2.5 mb-4 text-sm">
      <span className="text-gray-400">Active:</span>
      <span className="font-semibold font-mono text-[#818cf8]">{branch}</span>
      {ahead != null && ahead > 0 && (
        <span className="text-green-400 text-xs">↑ {ahead} ahead of main</span>
      )}
      {behind != null && behind > 0 && (
        <span className="text-yellow-400 text-xs">↓ {behind} behind main</span>
      )}
      <span className="flex-1" />
      {children}
    </div>
  );
}