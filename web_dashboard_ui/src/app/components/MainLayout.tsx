import { useEffect, useState } from 'react';
import { Outlet } from 'react-router';
import { Menu } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { fetchLiveNodes } from '../data/liveApi';
import { systemHealth as fallbackSystemHealth, systemProfile } from '../data/mockData';

export function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [systemHealth, setSystemHealth] = useState(fallbackSystemHealth);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const live = await fetchLiveNodes();
        if (!cancelled) {
          setSystemHealth(live.systemHealth);
        }
      } catch {
        // Keep fallback data if API is temporarily unavailable.
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

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="lg:hidden">
          <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <Menu className="w-5 h-5 text-gray-900" />
            </button>
            <div>
              <h1 className="font-semibold text-gray-900">{systemProfile.title}</h1>
            </div>
          </div>
        </div>
        <div className="hidden lg:block">
          <TopBar systemHealth={systemHealth} />
        </div>
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
