import { useEffect, useMemo, useState } from 'react';
import { Camera, Maximize2 } from 'lucide-react';
import { StatusBadge } from '../components/StatusBadge';
import { fetchLiveEvents, fetchLiveNodes, sendCameraControl } from '../data/liveApi';
import {
  cameraFeeds as fallbackCameraFeeds,
  detectionPipelines as fallbackDetectionPipelines,
  recentEvents as fallbackRecentEvents,
  type Alert,
  type CameraFeed,
  type DetectionPipeline,
  type Room,
} from '../data/mockData';

type FullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: () => Promise<void> | void;
  msRequestFullscreen?: () => Promise<void> | void;
};

type FullscreenDocument = Document & {
  webkitFullscreenElement?: Element | null;
  msFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => Promise<void> | void;
  msExitFullscreen?: () => Promise<void> | void;
};

type LockableScreen = Screen & {
  orientation?: ScreenOrientation & {
    lock?: (orientation: string) => Promise<void>;
    unlock?: () => void;
  };
};

export function LiveMonitoring() {
  const [events, setEvents] = useState<Alert[]>(fallbackRecentEvents);
  const [cameraFeeds, setCameraFeeds] = useState<CameraFeed[]>(fallbackCameraFeeds);
  const [detectionPipelines, setDetectionPipelines] = useState<DetectionPipeline[]>(
    fallbackDetectionPipelines,
  );
  const [flashStateByNode, setFlashStateByNode] = useState<Record<string, boolean>>({});
  const [controlPendingByNode, setControlPendingByNode] = useState<Record<string, boolean>>({});
  const [controlFeedbackByNode, setControlFeedbackByNode] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [eventsLive, nodesLive] = await Promise.all([fetchLiveEvents(250), fetchLiveNodes()]);
        if (cancelled) {
          return;
        }
        const mergedEvents = [...eventsLive.alerts, ...eventsLive.events].sort(
          (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
        );
        setEvents(mergedEvents);
        setCameraFeeds(nodesLive.cameraFeeds);
        setDetectionPipelines(nodesLive.detectionPipelines);
      } catch {
        // Keep fallback data if API is unavailable.
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 12000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const eventsByRoom = useMemo(() => {
    return events.reduce<Record<string, Alert[]>>((acc, event) => {
      const key = String(event.location || '');
      if (!acc[key]) {
        acc[key] = [];
      }
      acc[key].push(event);
      return acc;
    }, {});
  }, [events]);

  const eventsForRoom = (room: Room) => (eventsByRoom[String(room)] || []).slice(0, 5);
  const eventsForNode = (nodeId: string) => events.filter((event) => event.sourceNode === nodeId);
  const isFreshEvent = (timestamp: string, maxAgeSeconds = 90) => {
    const ageMs = Date.now() - new Date(timestamp).getTime();
    if (!Number.isFinite(ageMs)) {
      return false;
    }
    return ageMs <= maxAgeSeconds * 1000;
  };

  const lockLandscapeIfPossible = async () => {
    const lockableScreen = window.screen as LockableScreen;
    const locker = lockableScreen.orientation?.lock;
    if (!locker) {
      return false;
    }
    try {
      await locker.call(lockableScreen.orientation, 'landscape');
      return true;
    } catch {
      return false;
    }
  };

  const unlockOrientationIfPossible = () => {
    const lockableScreen = window.screen as LockableScreen;
    try {
      lockableScreen.orientation?.unlock?.();
    } catch {
      // Ignore unlock errors.
    }
  };

  useEffect(() => {
    const onFullscreenChange = () => {
      const fsDoc = document as FullscreenDocument;
      const currentFullscreen =
        fsDoc.fullscreenElement || fsDoc.webkitFullscreenElement || fsDoc.msFullscreenElement || null;
      if (!currentFullscreen) {
        unlockOrientationIfPossible();
      }
    };

    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange as EventListener);
    document.addEventListener('MSFullscreenChange', onFullscreenChange as EventListener);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', onFullscreenChange as EventListener);
      document.removeEventListener('MSFullscreenChange', onFullscreenChange as EventListener);
    };
  }, []);

  const toggleFullscreen = async (target: HTMLElement) => {
    const fsDoc = document as FullscreenDocument;
    const activeFsElement =
      fsDoc.fullscreenElement || fsDoc.webkitFullscreenElement || fsDoc.msFullscreenElement || null;

    if (activeFsElement === target) {
      if (fsDoc.exitFullscreen) {
        await fsDoc.exitFullscreen();
        return;
      }
      if (fsDoc.webkitExitFullscreen) {
        await fsDoc.webkitExitFullscreen();
        return;
      }
      if (fsDoc.msExitFullscreen) {
        await fsDoc.msExitFullscreen();
      }
      unlockOrientationIfPossible();
      return;
    }

    if (activeFsElement && fsDoc.exitFullscreen) {
      await fsDoc.exitFullscreen();
    }

    const fsTarget = target as FullscreenElement;
    if (fsTarget.requestFullscreen) {
      await fsTarget.requestFullscreen();
    } else if (fsTarget.webkitRequestFullscreen) {
      await fsTarget.webkitRequestFullscreen();
    } else if (fsTarget.msRequestFullscreen) {
      await fsTarget.msRequestFullscreen();
    }
    await lockLandscapeIfPossible();
  };

  const handleLightToggle = async (nodeId: string, turnOn: boolean) => {
    if (controlPendingByNode[nodeId]) {
      return;
    }

    setControlPendingByNode((prev) => ({ ...prev, [nodeId]: true }));
    setControlFeedbackByNode((prev) => ({ ...prev, [nodeId]: 'Sending command...' }));
    try {
      await sendCameraControl(nodeId, turnOn ? 'flash_on' : 'flash_off');
      setFlashStateByNode((prev) => ({ ...prev, [nodeId]: turnOn }));
      setControlFeedbackByNode((prev) => ({ ...prev, [nodeId]: turnOn ? 'Light turned ON.' : 'Light turned OFF.' }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to send camera command.';
      setControlFeedbackByNode((prev) => ({ ...prev, [nodeId]: message }));
    } finally {
      setControlPendingByNode((prev) => ({ ...prev, [nodeId]: false }));
    }
  };

  const CameraPanel = ({
    location,
    nodeId,
    streamPath,
    status,
  }: {
    location: Room;
    nodeId: string;
    streamPath?: string;
    status: CameraFeed['status'];
  }) => {
    const events = eventsForRoom(location);
    const nodeEvents = eventsForNode(nodeId);
    const isOnline = status === 'online';
    const lightState = flashStateByNode[nodeId];
    const lightLabel = lightState == null ? 'Light state unknown' : (lightState ? 'Light: ON' : 'Light: OFF');
    const latestFaceEvent = nodeEvents.find(
      (event) => event.eventCode === 'UNKNOWN' || event.eventCode === 'AUTHORIZED',
    );
    const latestFlameEvent = nodeEvents.find((event) => event.eventCode === 'FLAME_SIGNAL');

    const hasFreshFace = Boolean(latestFaceEvent && isFreshEvent(latestFaceEvent.timestamp));
    const faceLabel = hasFreshFace
      ? `Face: ${latestFaceEvent?.eventCode === 'UNKNOWN' ? 'UNKNOWN' : 'AUTHORIZED'}`
      : 'Face: IDLE';
    const faceSeverity: 'warning' | 'online' | 'info' = hasFreshFace
      ? (latestFaceEvent?.eventCode === 'UNKNOWN' ? 'warning' : 'online')
      : 'info';

    const hasFreshFlame = Boolean(latestFlameEvent && isFreshEvent(latestFlameEvent.timestamp));
    const flameLabel = hasFreshFlame ? 'Flame: DETECTED' : 'Flame: IDLE';
    const flameSeverity: 'warning' | 'info' = hasFreshFlame ? 'warning' : 'info';

    return (
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div
          className="relative bg-gray-900 aspect-video flex items-center justify-center"
          data-camera-frame="true"
        >
          {streamPath && (
            <img
              src={streamPath}
              alt={`${location} live feed`}
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          <Camera className="w-16 h-16 text-gray-600" />

          <div className="absolute top-4 left-4 flex items-center gap-2">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-600 text-white text-sm font-medium">
              <span className="w-2 h-2 bg-white rounded-full animate-pulse" />
              LIVE
            </span>
            <StatusBadge severity={isOnline ? 'online' : 'offline'} label={nodeId} size="sm" />
          </div>

          <div className="absolute top-4 right-4 flex flex-col gap-2">
            <StatusBadge severity={faceSeverity} label={faceLabel} size="sm" />
            <StatusBadge severity={flameSeverity} label={flameLabel} size="sm" />
          </div>

          <button
            onClick={(event) => {
              const frame = event.currentTarget.closest('[data-camera-frame="true"]');
              if (frame instanceof HTMLElement) {
                void toggleFullscreen(frame);
              }
            }}
            className="absolute bottom-4 right-4 p-2 bg-white/90 hover:bg-white rounded-lg transition-colors"
            title="Toggle Fullscreen"
            aria-label="Toggle Fullscreen"
          >
            <Maximize2 className="w-5 h-5 text-gray-900" />
          </button>

          <div className="absolute bottom-4 left-4 px-3 py-1.5 bg-black/60 text-white text-sm rounded">
            {new Date().toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })}
          </div>
        </div>

        <div className="p-4 border-t border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-gray-900">{location}</h3>
              <p className="text-sm text-gray-600">Night-vision stream (MQTT event mode)</p>
            </div>
            <div className="text-right text-sm">
              <p className="text-gray-500">Node</p>
              <p className="font-medium text-gray-900">{nodeId}</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 mb-4">
            <button
              onClick={() => {
                void handleLightToggle(nodeId, true);
              }}
              disabled={!isOnline || Boolean(controlPendingByNode[nodeId])}
              className="px-3 py-1.5 text-xs font-medium rounded-md border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:bg-gray-100 disabled:text-gray-400 disabled:border-gray-200 disabled:cursor-not-allowed"
            >
              Light ON
            </button>
            <button
              onClick={() => {
                void handleLightToggle(nodeId, false);
              }}
              disabled={!isOnline || Boolean(controlPendingByNode[nodeId])}
              className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:border-gray-200 disabled:cursor-not-allowed"
            >
              Light OFF
            </button>
            <span className="text-xs text-gray-600">
              {controlPendingByNode[nodeId] ? 'Sending...' : (controlFeedbackByNode[nodeId] || lightLabel)}
            </span>
          </div>

          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-900">Recent Activity</h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {events.length > 0 ? (
                events.map((event) => (
                  <div key={event.id} className="flex items-start gap-3 p-2 bg-gray-50 rounded-lg">
                    <div className="flex-shrink-0 w-1.5 h-1.5 bg-blue-600 rounded-full mt-1.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium text-gray-900">{event.title}</p>
                        <StatusBadge severity={event.severity} label={event.eventCode} size="sm" />
                      </div>
                      <p className="text-xs text-gray-600 mt-0.5">{formatTime(event.timestamp)}</p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-gray-500 text-center py-4">No recent activity</p>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const getPipelineSeverity = (state: 'active' | 'degraded' | 'offline') => {
    if (state === 'active') return 'online';
    if (state === 'degraded') return 'warning';
    return 'offline';
  };

  return (
    <div className="p-4 md:p-8 space-y-8">
      <div>
        <h2 className="text-2xl font-semibold text-gray-900">Live Monitoring</h2>
        <p className="text-gray-600 mt-1">
          Real-time camera view with intruder and fire evidence timeline.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {cameraFeeds.map((feed) => (
          <CameraPanel
            key={feed.nodeId}
            location={feed.location}
            nodeId={feed.nodeId}
            streamPath={feed.streamAvailable ? feed.streamPath : ''}
            status={feed.status}
          />
        ))}
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Detection Pipelines</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {detectionPipelines.map((pipeline) => (
            <div key={pipeline.name} className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-gray-900">{pipeline.name}</p>
                <StatusBadge
                  severity={getPipelineSeverity(pipeline.state)}
                  label={pipeline.state.toUpperCase()}
                  size="sm"
                />
              </div>
              <p className="text-xs text-gray-600 mt-2">{pipeline.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
