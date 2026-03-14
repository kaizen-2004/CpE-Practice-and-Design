import { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Users, Flame, AlertTriangle, Siren, Timer, ShieldCheck, type LucideIcon } from 'lucide-react';
import { fetchDailyStats } from '../data/liveApi';
import { dailyStats as fallbackDailyStats } from '../data/mockData';

export function Statistics() {
  const [dailyStats, setDailyStats] = useState(fallbackDailyStats);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const stats = await fetchDailyStats(7);
        if (!cancelled && stats.length > 0) {
          setDailyStats(stats);
        }
      } catch {
        // Keep fallback data if API is unavailable.
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 20000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const totals = dailyStats.reduce(
    (acc, day) => {
      acc.authorized += day.authorizedFaces;
      acc.unknown += day.unknownDetections;
      acc.flame += day.flameSignals;
      acc.smoke += day.smokeHighEvents;
      acc.fireAlerts += day.fireAlerts;
      acc.intruderAlerts += day.intruderAlerts;
      acc.responseSeconds += day.avgResponseSeconds;
      return acc;
    },
    {
      authorized: 0,
      unknown: 0,
      flame: 0,
      smoke: 0,
      fireAlerts: 0,
      intruderAlerts: 0,
      responseSeconds: 0,
    },
  );

  const avgResponse = dailyStats.length > 0 ? totals.responseSeconds / dailyStats.length : 0;

  const chartData = dailyStats.map((day) => ({
    date: new Date(day.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    Authorized: day.authorizedFaces,
    Unknown: day.unknownDetections,
    Flame: day.flameSignals,
    Smoke: day.smokeHighEvents,
    FireAlerts: day.fireAlerts,
    IntruderAlerts: day.intruderAlerts,
  }));

  const StatCard = ({
    title,
    value,
    icon: Icon,
    color,
  }: {
    title: string;
    value: number;
    icon: LucideIcon;
    color: string;
  }) => (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">{title}</p>
          <p className="text-2xl font-semibold text-gray-900 mt-1">{value}</p>
          <p className="text-xs text-gray-500 mt-1">Last 7 days</p>
        </div>
        <div className={`w-12 h-12 ${color} rounded-lg flex items-center justify-center`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  );

  return (
    <div className="p-4 md:p-8 space-y-8">
      <div>
        <h2 className="text-2xl font-semibold text-gray-900">Statistics</h2>
        <p className="text-gray-600 mt-1">
          Daily summary aligned with thesis objectives and system performance indicators.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Authorized Face Detections"
          value={totals.authorized}
          icon={Users}
          color="bg-green-100 text-green-600"
        />
        <StatCard
          title="Unknown Detections"
          value={totals.unknown}
          icon={AlertTriangle}
          color="bg-orange-100 text-orange-600"
        />
        <StatCard
          title="Fire Fusion Alerts"
          value={totals.fireAlerts}
          icon={Flame}
          color="bg-red-100 text-red-600"
        />
        <StatCard
          title="Intruder Fusion Alerts"
          value={totals.intruderAlerts}
          icon={Siren}
          color="bg-blue-100 text-blue-600"
        />
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-900">Face Identification Trend</h3>
          <p className="text-sm text-gray-600 mt-1">Authorized versus unknown detections per day</p>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} id="face-trends-chart">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
            <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                padding: '8px 12px',
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="Authorized"
              stroke="#10b981"
              strokeWidth={2}
              dot={{ fill: '#10b981', r: 4 }}
              id="line-authorized"
            />
            <Line
              type="monotone"
              dataKey="Unknown"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={{ fill: '#f59e0b', r: 4 }}
              id="line-unknown"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900">Fire Evidence Events</h3>
            <p className="text-sm text-gray-600 mt-1">Visual flame and smoke-high counts</p>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData} id="fire-evidence-chart">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
              <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  padding: '8px 12px',
                }}
              />
              <Legend />
              <Bar dataKey="Flame" fill="#ef4444" radius={[4, 4, 0, 0]} id="bar-flame" />
              <Bar dataKey="Smoke" fill="#6b7280" radius={[4, 4, 0, 0]} id="bar-smoke" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900">Fusion Alert Outputs</h3>
            <p className="text-sm text-gray-600 mt-1">Final intruder/fire classification counts</p>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData} id="fusion-alert-chart">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
              <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  padding: '8px 12px',
                }}
              />
              <Legend />
              <Bar
                dataKey="FireAlerts"
                fill="#dc2626"
                radius={[4, 4, 0, 0]}
                id="bar-fire-alerts"
              />
              <Bar
                dataKey="IntruderAlerts"
                fill="#2563eb"
                radius={[4, 4, 0, 0]}
                id="bar-intruder-alerts"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-6">Performance Metrics</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 flex items-center gap-2">
                <Timer className="w-4 h-4" /> Average Response Time
              </span>
              <span className="font-semibold text-gray-900">{avgResponse.toFixed(2)}s</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-green-600" style={{ width: '84%' }} />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4" /> Face Identification Accuracy
              </span>
              <span className="font-semibold text-gray-900">96.4%</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-green-600" style={{ width: '96.4%' }} />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Fire Detection False Positive</span>
              <span className="font-semibold text-gray-900">3.1%</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-orange-600" style={{ width: '3.1%' }} />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Fire Detection False Negative</span>
              <span className="font-semibold text-gray-900">4.2%</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-orange-600" style={{ width: '4.2%' }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
