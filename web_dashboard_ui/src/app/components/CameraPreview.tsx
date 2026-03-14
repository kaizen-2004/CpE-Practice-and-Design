import { Camera, Eye } from 'lucide-react';

interface CameraPreviewProps {
  location: 'Living Room' | 'Door Entrance Area';
  status: 'online' | 'offline';
  nodeId?: string;
  caption?: string;
  onViewLive?: () => void;
}

export function CameraPreview({ location, status, nodeId, caption, onViewLive }: CameraPreviewProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      {/* Camera placeholder */}
      <div className="relative bg-gray-900 aspect-video flex items-center justify-center">
        <Camera className="w-12 h-12 text-gray-600" />
        <div className="absolute top-3 left-3">
          <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium ${
            status === 'online' ? 'bg-green-500 text-white' : 'bg-gray-500 text-white'
          }`}>
            <span className="w-1.5 h-1.5 bg-white rounded-full"></span>
            {status === 'online' ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
        {onViewLive && (
          <button
            onClick={onViewLive}
            className="absolute bottom-3 right-3 px-3 py-1.5 bg-white/90 hover:bg-white text-gray-900 text-sm rounded-lg flex items-center gap-1.5 transition-colors"
          >
            <Eye className="w-4 h-4" />
            View Live
          </button>
        )}
      </div>
      {/* Camera info */}
      <div className="p-4">
        <h4 className="font-semibold text-gray-900">{location}</h4>
        <p className="text-sm text-gray-600 mt-1">{caption || 'Night Vision Camera'}</p>
        {nodeId && <p className="text-xs text-gray-500 mt-1">Node: {nodeId}</p>}
      </div>
    </div>
  );
}
