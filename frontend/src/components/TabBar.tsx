import type { ReactNode } from 'react';

interface Tab {
  id: string;
  label: string;
}

interface TabBarProps {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
  rightAction?: ReactNode;
}

export function TabBar({ tabs, active, onChange, rightAction }: TabBarProps) {
  return (
    <div className="flex gap-0 border-b border-[#2a2b36] mb-4">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`px-4 py-2 text-sm border-b-2 -mb-px cursor-pointer transition-colors ${
            active === tab.id
              ? 'text-white border-[#6366f1]'
              : 'text-gray-400 border-transparent hover:text-gray-300'
          }`}
        >
          {tab.label}
        </button>
      ))}
      {rightAction && <div className="ml-auto flex items-center">{rightAction}</div>}
    </div>
  );
}