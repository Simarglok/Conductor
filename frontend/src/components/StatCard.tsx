export type StatCardColor = 'green' | 'red' | 'yellow' | 'blue';

const colorClasses: Record<StatCardColor, string> = {
  green: 'text-[#22c55e]',
  red: 'text-[#ef4444]',
  yellow: 'text-[#eab308]',
  blue: 'text-[#3b82f6]',
};

interface StatCardProps {
  value: number | string;
  label: string;
  color?: StatCardColor;
}

export function StatCard({ value, label, color = 'blue' }: StatCardProps) {
  return (
    <div className="bg-[#1a1b23] border border-[#2a2b36] rounded-lg p-3">
      <div className={`text-2xl font-bold ${colorClasses[color]}`}>{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  );
}