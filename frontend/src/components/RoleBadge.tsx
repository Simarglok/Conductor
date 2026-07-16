const roleColors: Record<string, string> = {
  super_admin: 'bg-indigo-900/50 text-indigo-300 border-indigo-700',
  project_admin: 'bg-indigo-900/50 text-indigo-300 border-indigo-700',
  maintainer: 'bg-green-900/50 text-green-400 border-green-700',
  developer: 'bg-blue-900/50 text-blue-400 border-blue-700',
  viewer: 'bg-gray-800 text-gray-300 border-gray-700',
};

interface RoleBadgeProps {
  role: string;
}

export function RoleBadge({ role }: RoleBadgeProps) {
  const classes =
    roleColors[role] ?? 'bg-[#6366f1]/20 text-[#818cf8] border-[#6366f1]/40';

  return (
    <span
      className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full border ${classes}`}
    >
      {role.replace(/_/g, ' ')}
    </span>
  );
}