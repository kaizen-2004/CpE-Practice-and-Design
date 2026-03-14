// Mock data aligned to the thesis system architecture and event model.

export type SeverityLevel = 'critical' | 'warning' | 'normal' | 'info';
export type EventType = 'intruder' | 'fire' | 'sensor' | 'authorized' | 'system';
export type Room = 'Living Room' | 'Door Entrance Area' | string;
export type EventCode = string;
export type NodeId = string;

export interface Alert {
  id: string;
  timestamp: string;
  severity: SeverityLevel;
  type: EventType;
  eventCode: EventCode;
  sourceNode: NodeId;
  location: Room;
  title: string;
  description: string;
  acknowledged: boolean;
  responseTimeMs?: number;
  confidence?: number;
  fusionEvidence?: string[];
}

export interface KPI {
  label: string;
  value: number;
  trend?: number;
  icon: string;
  subtitle?: string;
}

export interface SensorStatus {
  id: NodeId;
  name: string;
  location: Room | 'System';
  type: 'camera' | 'smoke' | 'force';
  status: 'online' | 'offline' | 'warning';
  lastUpdate: string;
  note: string;
}

export interface ServiceStatus {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'warning';
  endpoint: string;
  lastUpdate: string;
  detail: string;
}

export interface DailyStats {
  date: string;
  authorizedFaces: number;
  unknownDetections: number;
  flameSignals: number;
  smokeHighEvents: number;
  fireAlerts: number;
  intruderAlerts: number;
  avgResponseSeconds: number;
}

export interface CameraFeed {
  location: Room;
  nodeId: 'cam_indoor' | 'cam_outdoor';
  status: 'online' | 'offline';
  quality: string;
  fps: number;
  latencyMs: number;
  streamPath?: string;
  streamAvailable?: boolean;
}

export interface DetectionPipeline {
  name: string;
  state: 'active' | 'degraded' | 'offline';
  detail: string;
}

export interface SystemHealth {
  raspberryPi: 'online' | 'offline';
  mqtt: 'connected' | 'disconnected';
  ingest: 'online' | 'offline';
  lastSync: string;
  uptime: string;
}

export interface AuthorizedProfile {
  id: string;
  dbId?: number;
  label: string;
  role: string;
  enrolledAt: string;
  sampleCount?: number;
}

export interface RuntimeSetting {
  key: string;
  value: string;
  description: string;
}

export const systemProfile = {
  title: 'Condo Monitoring Dashboard',
  subtitle: 'Real-Time Intruder and Fire Monitoring (Raspberry Pi + MQTT)',
  monitoredAreas: ['Living Room', 'Door Entrance Area'],
  transport: 'Wi-Fi MQTT (thesis/v1)',
  apiContract: 'POST /api/sensors/event',
};

export const mockAlerts: Alert[] = [
  {
    id: 'alert-001',
    timestamp: '2026-03-10T14:23:15Z',
    severity: 'critical',
    type: 'intruder',
    eventCode: 'INTRUDER',
    sourceNode: 'cam_outdoor',
    location: 'Door Entrance Area',
    title: 'Intruder Fusion Alert',
    description: '2-of-3 intrusion evidence matched within fusion window.',
    acknowledged: false,
    responseTimeMs: 1300,
    confidence: 94,
    fusionEvidence: ['outdoor unknown', 'door-force'],
  },
  {
    id: 'alert-002',
    timestamp: '2026-03-10T12:45:30Z',
    severity: 'warning',
    type: 'fire',
    eventCode: 'FIRE',
    sourceNode: 'cam_indoor',
    location: 'Living Room',
    title: 'Fire Fusion Alert',
    description: 'Indoor flame signal and smoke-high event were both detected.',
    acknowledged: true,
    responseTimeMs: 1800,
    confidence: 91,
    fusionEvidence: ['FLAME_SIGNAL (cam_indoor)', 'SMOKE_HIGH (mq2_living)'],
  },
  {
    id: 'alert-003',
    timestamp: '2026-03-10T09:15:00Z',
    severity: 'normal',
    type: 'authorized',
    eventCode: 'AUTHORIZED',
    sourceNode: 'cam_outdoor',
    location: 'Door Entrance Area',
    title: 'Authorized Entry',
    description: 'Authorized face recognized at entrance camera.',
    acknowledged: true,
    confidence: 97,
  },
];

export const recentEvents: Alert[] = [
  ...mockAlerts,
  {
    id: 'event-004',
    timestamp: '2026-03-10T14:20:10Z',
    severity: 'warning',
    type: 'sensor',
    eventCode: 'DOOR_FORCE',
    sourceNode: 'door_force',
    location: 'Door Entrance Area',
    title: 'Door Force Detected',
    description: 'Door-force sensor exceeded impact threshold.',
    acknowledged: false,
  },
  {
    id: 'event-005',
    timestamp: '2026-03-10T12:44:54Z',
    severity: 'warning',
    type: 'sensor',
    eventCode: 'SMOKE_HIGH',
    sourceNode: 'mq2_living',
    location: 'Living Room',
    title: 'Smoke High Event',
    description: 'MQ-2 sensor value crossed configured smoke threshold.',
    acknowledged: true,
  },
  {
    id: 'event-006',
    timestamp: '2026-03-10T12:44:21Z',
    severity: 'warning',
    type: 'fire',
    eventCode: 'FLAME_SIGNAL',
    sourceNode: 'cam_indoor',
    location: 'Living Room',
    title: 'Flame Signal',
    description: 'Indoor camera detected possible flame-like region.',
    acknowledged: true,
  },
  {
    id: 'event-007',
    timestamp: '2026-03-10T10:17:02Z',
    severity: 'normal',
    type: 'sensor',
    eventCode: 'SMOKE_NORMAL',
    sourceNode: 'mq2_living',
    location: 'Living Room',
    title: 'Smoke Returned to Normal',
    description: 'Smoke reading dropped below the clear threshold.',
    acknowledged: true,
  },
  {
    id: 'event-008',
    timestamp: '2026-03-10T08:30:22Z',
    severity: 'info',
    type: 'system',
    eventCode: 'CAM_HEARTBEAT',
    sourceNode: 'cam_outdoor',
    location: 'Door Entrance Area',
    title: 'Outdoor Camera Heartbeat',
    description: 'Camera node heartbeat received through MQTT ingest.',
    acknowledged: true,
  },
  {
    id: 'event-009',
    timestamp: '2026-03-10T07:45:10Z',
    severity: 'warning',
    type: 'intruder',
    eventCode: 'UNKNOWN',
    sourceNode: 'cam_indoor',
    location: 'Living Room',
    title: 'Unknown Face Detected',
    description: 'Indoor camera marked an unrecognized face.',
    acknowledged: true,
    confidence: 88,
  },
];

export const kpiData: KPI[] = [
  {
    label: 'Authorized Faces',
    value: 31,
    trend: 4,
    icon: 'UserCheck',
    subtitle: 'Today',
  },
  {
    label: 'Unknown Detections',
    value: 2,
    trend: -1,
    icon: 'UserX',
    subtitle: 'Today',
  },
  {
    label: 'Fire Fusion Alerts',
    value: 1,
    trend: 0,
    icon: 'ShieldAlert',
    subtitle: 'Today',
  },
  {
    label: 'Active Nodes',
    value: 5,
    trend: 0,
    icon: 'Activity',
    subtitle: '5 total nodes',
  },
];

export const sensorStatuses: SensorStatus[] = [
  {
    id: 'cam_outdoor',
    name: 'Outdoor Night-Vision Camera',
    location: 'Door Entrance Area',
    type: 'camera',
    status: 'online',
    lastUpdate: '2026-03-10T14:30:00Z',
    note: 'Face detection active',
  },
  {
    id: 'cam_indoor',
    name: 'Indoor Night-Vision Camera',
    location: 'Living Room',
    type: 'camera',
    status: 'online',
    lastUpdate: '2026-03-10T14:30:00Z',
    note: 'Flame detection active',
  },
  {
    id: 'mq2_living',
    name: 'MQ-2 Smoke Sensor (Living)',
    location: 'Living Room',
    type: 'smoke',
    status: 'online',
    lastUpdate: '2026-03-10T14:29:45Z',
    note: 'Baseline stable',
  },
  {
    id: 'mq2_door',
    name: 'MQ-2 Smoke Sensor (Entrance)',
    location: 'Door Entrance Area',
    type: 'smoke',
    status: 'online',
    lastUpdate: '2026-03-10T14:29:42Z',
    note: 'Baseline stable',
  },
  {
    id: 'door_force',
    name: 'Door-Force Sensor',
    location: 'Door Entrance Area',
    type: 'force',
    status: 'warning',
    lastUpdate: '2026-03-10T14:29:50Z',
    note: 'High vibration near threshold',
  },
];

export const serviceStatuses: ServiceStatus[] = [
  {
    id: 'service-001',
    name: 'Mosquitto Broker',
    status: 'online',
    endpoint: 'mqtt://127.0.0.1:1883',
    lastUpdate: '2026-03-10T14:30:12Z',
    detail: 'Topic root: thesis/v1',
  },
  {
    id: 'service-002',
    name: 'MQTT Ingest Service',
    status: 'online',
    endpoint: 'pi/mqtt_ingest.py',
    lastUpdate: '2026-03-10T14:30:11Z',
    detail: 'Forwarding to POST /api/sensors/event',
  },
  {
    id: 'service-003',
    name: 'Flask API + Dashboard',
    status: 'online',
    endpoint: 'pi/app.py',
    lastUpdate: '2026-03-10T14:30:15Z',
    detail: 'SQLite and alert fusion available',
  },
  {
    id: 'service-004',
    name: 'Vision Runtime',
    status: 'warning',
    endpoint: 'pi/vision_runtime.py',
    lastUpdate: '2026-03-10T14:29:58Z',
    detail: 'Indoor stream latency elevated',
  },
];

export const cameraFeeds: CameraFeed[] = [
  {
    location: 'Door Entrance Area',
    nodeId: 'cam_outdoor',
    status: 'online',
    quality: 'ESP32-CAM stream',
    fps: 22,
    latencyMs: 140,
  },
  {
    location: 'Living Room',
    nodeId: 'cam_indoor',
    status: 'online',
    quality: 'ESP32-CAM stream',
    fps: 20,
    latencyMs: 170,
  },
];

export const detectionPipelines: DetectionPipeline[] = [
  {
    name: 'Face Recognition (OpenCV LBPH)',
    state: 'active',
    detail: 'Authorized vs unknown classification running',
  },
  {
    name: 'Visual Flame Detection',
    state: 'active',
    detail: 'Indoor frame analysis active',
  },
  {
    name: 'Smoke Sensor Ingest (MQ-2)',
    state: 'active',
    detail: 'Both nodes publishing to MQTT',
  },
  {
    name: 'Door-Force Event Monitor',
    state: 'degraded',
    detail: 'Intermittent vibration noise, monitoring threshold',
  },
];

export const dailyStats: DailyStats[] = [
  {
    date: '2026-03-04',
    authorizedFaces: 23,
    unknownDetections: 2,
    flameSignals: 0,
    smokeHighEvents: 0,
    fireAlerts: 0,
    intruderAlerts: 1,
    avgResponseSeconds: 1.7,
  },
  {
    date: '2026-03-05',
    authorizedFaces: 27,
    unknownDetections: 1,
    flameSignals: 0,
    smokeHighEvents: 1,
    fireAlerts: 0,
    intruderAlerts: 0,
    avgResponseSeconds: 1.5,
  },
  {
    date: '2026-03-06',
    authorizedFaces: 19,
    unknownDetections: 1,
    flameSignals: 0,
    smokeHighEvents: 0,
    fireAlerts: 0,
    intruderAlerts: 0,
    avgResponseSeconds: 1.4,
  },
  {
    date: '2026-03-07',
    authorizedFaces: 24,
    unknownDetections: 3,
    flameSignals: 1,
    smokeHighEvents: 0,
    fireAlerts: 0,
    intruderAlerts: 1,
    avgResponseSeconds: 2.1,
  },
  {
    date: '2026-03-08',
    authorizedFaces: 28,
    unknownDetections: 1,
    flameSignals: 0,
    smokeHighEvents: 0,
    fireAlerts: 0,
    intruderAlerts: 0,
    avgResponseSeconds: 1.4,
  },
  {
    date: '2026-03-09',
    authorizedFaces: 22,
    unknownDetections: 2,
    flameSignals: 0,
    smokeHighEvents: 1,
    fireAlerts: 0,
    intruderAlerts: 1,
    avgResponseSeconds: 1.8,
  },
  {
    date: '2026-03-10',
    authorizedFaces: 31,
    unknownDetections: 2,
    flameSignals: 1,
    smokeHighEvents: 1,
    fireAlerts: 1,
    intruderAlerts: 1,
    avgResponseSeconds: 1.6,
  },
];

export const authorizedProfiles: AuthorizedProfile[] = [
  {
    id: 'auth-001',
    label: 'Resident 01',
    role: 'Owner',
    enrolledAt: '2026-02-17',
  },
  {
    id: 'auth-002',
    label: 'Resident 02',
    role: 'Family',
    enrolledAt: '2026-02-20',
  },
  {
    id: 'auth-003',
    label: 'Caretaker',
    role: 'Authorized Guest',
    enrolledAt: '2026-02-24',
  },
];

export const runtimeSettings: RuntimeSetting[] = [
  {
    key: 'SENSOR_EVENT_URL',
    value: 'http://127.0.0.1:5000/api/sensors/event',
    description: 'Sensor event API endpoint',
  },
  {
    key: 'MQTT_TOPIC_ROOT',
    value: 'thesis/v1',
    description: 'MQTT publish/subscribe root topic',
  },
  {
    key: 'FIRE_FUSION_WINDOW',
    value: '120 seconds',
    description: 'Smoke + flame correlation window',
  },
  {
    key: 'INTRUDER_FUSION_WINDOW',
    value: '120 seconds',
    description: 'Unknown + door evidence correlation window',
  },
  {
    key: 'ALERT_COOLDOWN',
    value: '45 seconds',
    description: 'Intruder alert cooldown interval',
  },
  {
    key: 'FIRE_COOLDOWN',
    value: '75 seconds',
    description: 'Fire alert cooldown interval',
  },
];

export const systemHealth: SystemHealth = {
  raspberryPi: 'online',
  mqtt: 'connected',
  ingest: 'online',
  lastSync: '2026-03-10T14:30:15Z',
  uptime: '7d 14h 23m',
};
