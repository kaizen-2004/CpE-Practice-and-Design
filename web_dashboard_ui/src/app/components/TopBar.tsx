import { Wifi, WifiOff, Database, Clock, Server } from 'lucide-react';
import { systemProfile } from '../data/mockData';
import type { SystemHealth } from '../data/mockData';
import { StatusBadge } from './StatusBadge';

interface TopBarProps {
  systemHealth: SystemHealth;
}

export function TopBar({ systemHealth }: TopBarProps) {
  const formatLastSync = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    
    if (diffSecs < 60) return `${diffSecs}s ago`;
    if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)}m ago`;
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="bg-white border-b border-gray-200 px-4 md:px-8 py-4">
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3">
        <div>
          <h1 className="text-lg md:text-xl font-semibold text-gray-900">{systemProfile.title}</h1>
          <p className="text-xs md:text-sm text-gray-600">{systemProfile.subtitle}</p>
          <p className="text-xs text-gray-500 mt-1">
            Scope: {systemProfile.monitoredAreas.join(' + ')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 md:gap-5">
          <div className="flex items-center gap-2">
            {systemHealth.raspberryPi === 'online' ? (
              <Wifi className="w-4 h-4 text-green-600" />
            ) : (
              <WifiOff className="w-4 h-4 text-red-600" />
            )}
            <StatusBadge severity={systemHealth.raspberryPi} label="RPi" size="sm" />
          </div>

          <div className="flex items-center gap-2">
            <Database className={`w-4 h-4 ${systemHealth.mqtt === 'connected' ? 'text-green-600' : 'text-red-600'}`} />
            <StatusBadge severity={systemHealth.mqtt} label="MQTT" size="sm" />
          </div>

          <div className="flex items-center gap-2">
            <Server className={`w-4 h-4 ${systemHealth.ingest === 'online' ? 'text-green-600' : 'text-red-600'}`} />
            <StatusBadge severity={systemHealth.ingest} label="Ingest" size="sm" />
          </div>

          <div className="flex items-center gap-2 text-sm text-gray-700">
            <Clock className="w-4 h-4 text-blue-600" />
            <span className="font-medium">{formatLastSync(systemHealth.lastSync)}</span>
            <span className="text-gray-400">|</span>
            <span>{systemHealth.uptime}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
