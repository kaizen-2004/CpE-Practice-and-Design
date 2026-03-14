# IoT Security Monitoring Dashboard

A clean, modern web dashboard for monitoring real-time intruder and fire detection using IoT facial recognition with night-vision cameras.

## Flask Integration

This frontend is mounted into Flask and served from `/dashboard`.

- Build command: `npm run build`
- Build output: `web_dashboard_ui/dist`
- Flask serves the SPA and deep links (`/dashboard/*`) from that folder.
- Legacy Flask template dashboard is still available at `/dashboard-legacy`.

## Features

### 📊 Dashboard Overview
- **Critical Alert Panel**: Prioritized display of active alerts with severity levels (critical, warning, normal, info)
- **KPI Cards**: Real-time metrics for authorized faces, unknown detections, fire-related events, and active sensors
- **Camera Previews**: Live camera feed tiles for Living Room and Door Entrance Area
- **Recent Events**: Filterable event timeline with quick access to detailed views
- **Quick Actions**: Acknowledge alerts, view cameras, and export reports

### 📹 Live Monitoring
- **Dual Camera Feeds**: Real-time monitoring of Door Entrance Area and Living Room
- **Event Timeline**: Recent activity displayed beside each camera feed
- **Detection Status**: Visual indicators for face recognition, flame detection, motion tracking, and night vision
- **Video Controls**: Fullscreen mode and quality indicators (FPS, latency)

### 🔔 Events & Alerts
- **Advanced Filtering**: Search by keyword, filter by severity and event type, date range selection
- **Event Table**: Comprehensive table view with sortable columns
- **Detail Modal**: Click any event to view full details including camera snapshot, sensor data, and action history
- **Acknowledgement Workflow**: Track which alerts have been reviewed

### 📡 Sensors & Device Status
- **Device Grid**: All connected sensors displayed with status, battery level, and last update time
- **Status Summary**: Quick overview of online, warning, and offline devices
- **Device Management**: Add new devices, run diagnostics, and export reports
- **Sensor Types**: Cameras, smoke detectors, motion sensors, and door force sensors

### 📈 Statistics
- **Detection Trends**: Line charts showing daily face recognition and threat detection activity
- **Event Distribution**: Bar charts comparing authorized vs unknown detections
- **Fire-Related Events**: Dedicated tracking for flame and smoke events
- **Performance Metrics**: System uptime, detection accuracy, and average response time

### ⚙️ Settings
- **Alert Settings**: Configure email, push, and critical alert notifications
- **Camera Settings**: Night vision mode, video quality, and recording duration
- **Detection Settings**: Adjustable confidence levels and sensitivity thresholds
- **Authorized Users**: Manage face recognition database
- **System Configuration**: Network settings, MQTT broker, and database backup

## Design Principles

### Visual Style
- **Light Theme**: Neutral gray-50 background with high-contrast text
- **Semantic Colors**: 
  - 🔴 Red = Critical alerts
  - 🟠 Orange = Warning status
  - 🟢 Green = Normal/healthy
  - 🔵 Blue = Informational
- **8px Spacing System**: Consistent padding and margins using Tailwind's default scale
- **Professional Typography**: Clear, readable fonts with strong visual hierarchy

### UX Principles
- **Information Priority**: High-risk information (fire/intrusion) displayed first
- **Minimal Clutter**: Generous whitespace and organized card layouts
- **Fast Scanning**: Clear section headers and color-coded severity badges
- **Progressive Disclosure**: Secondary details revealed on interaction
- **Always Accessible**: Primary actions always visible and easy to reach

### Responsive Design
- **Desktop First**: Optimized for security monitoring stations
- **Tablet Support**: Adaptive layouts for medium screens
- **Mobile Compatible**: Collapsible sidebar and touch-friendly controls
- **WCAG Compliant**: Proper contrast ratios and keyboard navigation

## Technical Stack

- **React 18.3.1** - UI framework
- **React Router 7** - Client-side routing with data mode
- **Tailwind CSS 4** - Utility-first styling
- **Recharts** - Data visualization
- **Lucide React** - Icon library
- **TypeScript** - Type safety

## Project Structure

```
/src/app/
├── components/          # Reusable UI components
│   ├── MainLayout.tsx   # App shell with sidebar and topbar
│   ├── Sidebar.tsx      # Navigation sidebar
│   ├── TopBar.tsx       # System health status bar
│   ├── AlertCard.tsx    # Alert/event card component
│   ├── StatusBadge.tsx  # Colored status badges
│   ├── KPICard.tsx      # Key performance indicator cards
│   └── CameraPreview.tsx # Camera feed preview tiles
├── pages/               # Route pages
│   ├── Dashboard.tsx    # Main overview page
│   ├── LiveMonitoring.tsx
│   ├── EventsAlerts.tsx
│   ├── SensorsStatus.tsx
│   ├── Statistics.tsx
│   ├── Settings.tsx
│   └── NotFound.tsx
├── data/
│   └── mockData.ts      # Mock data for demonstration
├── routes.ts            # React Router configuration
└── App.tsx              # Application entry point
```

## Key Components

### StatusBadge
Colored status indicators with semantic colors based on severity level.

### AlertCard
Displays alerts and events with severity indicators, location, timestamp, and acknowledgement actions.

### KPICard
Shows key metrics with trend indicators and icons.

### CameraPreview
Live camera feed preview with status overlay and view live button.

## Mock Data

The application uses comprehensive mock data to simulate:
- Real-time alerts and events
- Sensor status readings
- Daily statistics and trends
- System health metrics

## User Flow

1. **Dashboard** → View critical alerts and system overview
2. **Acknowledge Alert** → Click acknowledge button on active alerts
3. **View Details** → Click event to open detail modal
4. **Live Monitoring** → Navigate to camera feeds for real-time view
5. **Review History** → Access Events & Alerts for comprehensive timeline

## Accessibility

- High contrast text (WCAG AA compliant)
- Keyboard-friendly navigation
- Clear focus states
- Screen reader compatible semantic HTML
- Touch-friendly button sizes (min 44x44px)

## Future Enhancements

- Real backend integration (Flask API, MQTT broker)
- WebSocket for true real-time updates
- Video playback and recording access
- Advanced analytics and reporting
- Multi-user authentication and roles
- Email/SMS notification integration
- Mobile application

## License

© 2026 SecureHome - All rights reserved
