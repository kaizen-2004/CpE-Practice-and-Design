import { AlertTriangle, Flame, UserCheck, Bell } from 'lucide-react';
import type { Alert } from '../data/mockData';
import { StatusBadge } from './StatusBadge';

interface AlertCardProps {
  alert: Alert;
  onAcknowledge?: (id: string) => void;
  onClick?: () => void;
}

export function AlertCard({ alert, onAcknowledge, onClick }: AlertCardProps) {
  const getIcon = () => {
    switch (alert.type) {
      case 'intruder':
        return <AlertTriangle className="w-5 h-5" />;
      case 'fire':
        return <Flame className="w-5 h-5" />;
      case 'authorized':
        return <UserCheck className="w-5 h-5" />;
      default:
        return <Bell className="w-5 h-5" />;
    }
  };

  const getBorderColor = () => {
    switch (alert.severity) {
      case 'critical':
        return 'border-l-red-500';
      case 'warning':
        return 'border-l-orange-500';
      case 'normal':
        return 'border-l-green-500';
      default:
        return 'border-l-blue-500';
    }
  };

  const getIconBgColor = () => {
    switch (alert.severity) {
      case 'critical':
        return 'bg-red-50 text-red-600';
      case 'warning':
        return 'bg-orange-50 text-orange-600';
      case 'normal':
        return 'bg-green-50 text-green-600';
      default:
        return 'bg-blue-50 text-blue-600';
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div
      className={`bg-white rounded-lg border border-gray-200 ${getBorderColor()} border-l-4 p-4 hover:shadow-md transition-shadow ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-4">
        <div className={`rounded-lg p-2.5 ${getIconBgColor()}`}>
          {getIcon()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-1">
            <h4 className="font-semibold text-gray-900">{alert.title}</h4>
            <StatusBadge severity={alert.severity} label={alert.severity.toUpperCase()} size="sm" />
          </div>
          <p className="text-sm text-gray-600 mb-2">{alert.description}</p>
          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
            <span>{alert.location}</span>
            <span>Node: {alert.sourceNode}</span>
            <span>Code: {alert.eventCode}</span>
            <span>{formatTime(alert.timestamp)}</span>
          </div>
          {alert.fusionEvidence && alert.fusionEvidence.length > 0 && (
            <p className="text-xs text-gray-600 mt-2">
              Evidence: {alert.fusionEvidence.join(', ')}
            </p>
          )}
        </div>
        {!alert.acknowledged && onAcknowledge && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAcknowledge(alert.id);
            }}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap"
          >
            Acknowledge
          </button>
        )}
      </div>
    </div>
  );
}
