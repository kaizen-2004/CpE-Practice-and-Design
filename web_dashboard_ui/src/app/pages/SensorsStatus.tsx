import { useEffect, useState } from 'react';
import { Camera, Flame, Gauge, Server, WifiOff, CheckCircle2, AlertTriangle } from 'lucide-react';
import { fetchLiveNodes } from '../data/liveApi';
import {
  sensorStatuses as fallbackSensorStatuses,
  serviceStatuses as fallbackServiceStatuses,
} from '../data/mockData';
import type { SensorStatus } from '../data/mockData';
import { StatusBadge } from '../components/StatusBadge';

export function SensorsStatus() {
  const [sensorStatuses, setSensorStatuses] = useState(fallbackSensorStatuses);
  const [serviceStatuses, setServiceStatuses] = useState(fallbackServiceStatuses);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const live = await fetchLiveNodes();
        if (cancelled) {
          return;
        }
        setSensorStatuses(live.sensorStatuses);
        setServiceStatuses(live.serviceStatuses);
      } catch {
        // Keep fallback data if API is unavailable.
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const getIcon = (type: SensorStatus['type']) => {
    switch (type) {
      case 'camera':
        return <Camera className="w-6 h-6" />;
      case 'smoke':
        return <Flame className="w-6 h-6" />;
      case 'force':
        return <Gauge className="w-6 h-6" />;
    }
  };

  const getStatusColor = (status: SensorStatus['status']) => {
    switch (status) {
      case 'online':
        return 'bg-green-50 text-green-600';
      case 'offline':
        return 'bg-gray-50 text-gray-600';
      case 'warning':
        return 'bg-orange-50 text-orange-600';
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  const onlineNodes = sensorStatuses.filter((s) => s.status === 'online').length;
  const warningNodes = sensorStatuses.filter((s) => s.status === 'warning').length;
  const offlineNodes = sensorStatuses.filter((s) => s.status === 'offline').length;

  const onlineServices = serviceStatuses.filter((s) => s.status === 'online').length;

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-gray-900">Sensors & Nodes</h2>
        <p className="text-gray-600 mt-1">Operational status for all deployed nodes and runtime services.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <p className="text-sm text-gray-600">Online Nodes</p>
          <p className="text-3xl font-semibold text-green-600 mt-1">{onlineNodes}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <p className="text-sm text-gray-600">Warning Nodes</p>
          <p className="text-3xl font-semibold text-orange-600 mt-1">{warningNodes}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <p className="text-sm text-gray-600">Offline Nodes</p>
          <p className="text-3xl font-semibold text-gray-600 mt-1">{offlineNodes}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <p className="text-sm text-gray-600">Online Services</p>
          <p className="text-3xl font-semibold text-blue-600 mt-1">{onlineServices}</p>
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">Sensor Nodes</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sensorStatuses.map((sensor) => (
            <div key={sensor.id} className="bg-white rounded-lg border border-gray-200 p-5">
              <div className="flex items-start justify-between mb-4 gap-4">
                <div className="flex items-start gap-3">
                  <div className={`rounded-lg p-3 ${getStatusColor(sensor.status)}`}>{getIcon(sensor.type)}</div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{sensor.name}</h3>
                    <p className="text-sm text-gray-600 mt-0.5">{sensor.location}</p>
                    <p className="text-xs font-mono text-gray-500 mt-1">{sensor.id}</p>
                  </div>
                </div>
                <StatusBadge severity={sensor.status} label={sensor.status.toUpperCase()} size="sm" />
              </div>

              <div className="space-y-2 pt-4 border-t border-gray-200 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-600">Last Update</span>
                  <span className="font-medium text-gray-900">{formatTime(sensor.lastUpdate)}</span>
                </div>
                <div className="flex items-start justify-between gap-4">
                  <span className="text-gray-600">Node Note</span>
                  <span className="font-medium text-gray-900 text-right">{sensor.note}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">Runtime Services</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {serviceStatuses.map((service) => (
            <div key={service.id} className="bg-white rounded-lg border border-gray-200 p-5">
              <div className="flex items-start justify-between mb-4 gap-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg p-3 bg-blue-50 text-blue-600">
                    <Server className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{service.name}</h3>
                    <p className="text-xs font-mono text-gray-500 mt-1">{service.endpoint}</p>
                  </div>
                </div>
                <StatusBadge severity={service.status} label={service.status.toUpperCase()} size="sm" />
              </div>

              <div className="space-y-2 pt-4 border-t border-gray-200 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-600">Last Update</span>
                  <span className="font-medium text-gray-900">{formatTime(service.lastUpdate)}</span>
                </div>
                <div className="flex items-start justify-between gap-4">
                  <span className="text-gray-600">Detail</span>
                  <span className="font-medium text-gray-900 text-right">{service.detail}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-900 mb-4">Node Health Summary</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <div className="flex items-center gap-2 text-green-700">
            <CheckCircle2 className="w-4 h-4" />
            <span>Stable nodes: {onlineNodes}</span>
          </div>
          <div className="flex items-center gap-2 text-orange-700">
            <AlertTriangle className="w-4 h-4" />
            <span>Needs attention: {warningNodes}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-700">
            <WifiOff className="w-4 h-4" />
            <span>Offline nodes: {offlineNodes}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
