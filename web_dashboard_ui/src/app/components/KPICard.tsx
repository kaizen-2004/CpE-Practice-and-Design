import { 
  UserCheck, 
  UserX, 
  Flame, 
  Activity, 
  ShieldAlert,
  TrendingUp, 
  TrendingDown,
  Minus 
} from 'lucide-react';

interface KPICardProps {
  label: string;
  value: number;
  trend?: number;
  icon: string;
  subtitle?: string;
}

const iconMap = {
  UserCheck,
  UserX,
  Flame,
  Activity,
  ShieldAlert,
};

export function KPICard({ label, value, trend, icon, subtitle }: KPICardProps) {
  const IconComponent = iconMap[icon as keyof typeof iconMap];

  const getTrendIcon = () => {
    if (!trend || trend === 0) return <Minus className="w-4 h-4" />;
    if (trend > 0) return <TrendingUp className="w-4 h-4" />;
    return <TrendingDown className="w-4 h-4" />;
  };

  const getTrendColor = () => {
    if (!trend || trend === 0) return 'text-gray-500';
    // For security metrics, trends might have different meanings
    // Unknown detections going down is good, authorized faces going up is good
    if (label.includes('Unknown') || label.includes('Fire')) {
      return trend > 0 ? 'text-red-600' : 'text-green-600';
    }
    return trend > 0 ? 'text-green-600' : 'text-red-600';
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-gray-600 mb-1">{label}</p>
          <p className="text-3xl font-semibold text-gray-900">{value}</p>
          {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
          {trend !== undefined && (
            <div className={`flex items-center gap-1 mt-2 text-sm ${getTrendColor()}`}>
              {getTrendIcon()}
              <span>{trend > 0 ? '+' : ''}{trend} today</span>
            </div>
          )}
        </div>
        <div className="bg-blue-50 rounded-lg p-3">
          {IconComponent && <IconComponent className="w-6 h-6 text-blue-600" />}
        </div>
      </div>
    </div>
  );
}
