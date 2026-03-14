import { createBrowserRouter } from 'react-router';
import { MainLayout } from './components/MainLayout';
import { Dashboard } from './pages/Dashboard';
import { LiveMonitoring } from './pages/LiveMonitoring';
import { EventsAlerts } from './pages/EventsAlerts';
import { SensorsStatus } from './pages/SensorsStatus';
import { Statistics } from './pages/Statistics';
import { Settings } from './pages/Settings';
import { NotFound } from './pages/NotFound';

const routerBase = import.meta.env.BASE_URL.endsWith('/')
  ? import.meta.env.BASE_URL.slice(0, -1)
  : import.meta.env.BASE_URL;

export const router = createBrowserRouter([
  {
    path: '/',
    Component: MainLayout,
    children: [
      {
        index: true,
        Component: Dashboard,
      },
      {
        path: 'live',
        Component: LiveMonitoring,
      },
      {
        path: 'events',
        Component: EventsAlerts,
      },
      {
        path: 'sensors',
        Component: SensorsStatus,
      },
      {
        path: 'statistics',
        Component: Statistics,
      },
      {
        path: 'settings',
        Component: Settings,
      },
      {
        path: '*',
        Component: NotFound,
      },
    ],
  },
], {
  basename: routerBase || '/',
});
