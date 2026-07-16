type CheckStatus = 'success' | 'failure' | 'pending';

interface CheckBadgeProps {
  name: string;
  status: CheckStatus;
  duration?: string;
}

const statusDisplay: Record<CheckStatus, { icon: string; className: string }> = {
  success: { icon: '✅', className: 'text-green-400' },
  failure: { icon: '❌', className: 'text-red-400' },
  pending: { icon: '⏳', className: 'text-yellow-400' },
};

export function CheckBadge({ name, status, duration }: CheckBadgeProps) {
  const { icon, className } = statusDisplay[status];
  return (
    <span className={`text-xs font-medium ${className}`}>
      {icon} {name}
      {duration ? ` (${duration})` : ''}
    </span>
  );
}