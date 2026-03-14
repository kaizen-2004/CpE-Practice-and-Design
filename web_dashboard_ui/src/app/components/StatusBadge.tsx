import type { SeverityLevel } from '../data/mockData';

interface StatusBadgeProps {
  severity: SeverityLevel | 'online' | 'offline' | 'connected' | 'disconnected';
  label: string;
  size?: 'sm' | 'md' | 'lg';
}

export function StatusBadge({ severity, label, size = 'md' }: StatusBadgeProps) {
  const colors = {
    critical: 'bg-red-100 text-red-800 border-red-200',
    warning: 'bg-orange-100 text-orange-800 border-orange-200',
    normal: 'bg-green-100 text-green-800 border-green-200',
    info: 'bg-blue-100 text-blue-800 border-blue-200',
    online: 'bg-green-100 text-green-800 border-green-200',
    offline: 'bg-gray-100 text-gray-800 border-gray-200',
    connected: 'bg-green-100 text-green-800 border-green-200',
    disconnected: 'bg-red-100 text-red-800 border-red-200',
  };

  const sizes = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-3 py-1',
    lg: 'text-base px-4 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full border ${colors[severity]} ${sizes[size]} font-medium`}
    >
      {label}
    </span>
  );
}
