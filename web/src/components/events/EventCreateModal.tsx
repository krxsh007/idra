import React, { useState } from 'react';
import { X, PlusCircle, AlertCircle, MapPin } from 'lucide-react';
import { api } from '../../lib/api';
import { DisasterType, EpicenterPoint } from '../../types/api';

interface EventCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onStartLocationPick: (onPick: (coords: EpicenterPoint) => void) => void;
}

export const EventCreateModal: React.FC<EventCreateModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  onStartLocationPick,
}) => {
  const [name, setName] = useState('');
  const [disasterType, setDisasterType] = useState<DisasterType>('FLOOD');
  const [lon, setLon] = useState('80.225');
  const [lat, setLat] = useState('13.05');
  const [radiusM, setRadiusM] = useState('5000');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handlePickOnMap = () => {
    onStartLocationPick((coords) => {
      setLon(coords.lon.toFixed(5));
      setLat(coords.lat.toFixed(5));
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await api.createEvent({
        name,
        disaster_type: disasterType,
        epicenter: { lon: parseFloat(lon), lat: parseFloat(lat) },
        radius_m: parseInt(radiusM, 10),
        description: description || undefined,
      });
      setLoading(false);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setLoading(false);
      setError(err instanceof Error ? err.message : 'Failed to declare event');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-6">
          <div className="p-2.5 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/30">
            <PlusCircle className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">Declare Disaster Event</h2>
            <p className="text-xs text-slate-400">Initialize an active disaster monitoring perimeter (Admin)</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-950/60 border border-red-800/80 rounded-xl text-xs text-red-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block font-medium text-slate-300 mb-1">Event Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Cyclone Michaung Surge"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Disaster Type</label>
              <select
                value={disasterType}
                onChange={(e) => setDisasterType(e.target.value as DisasterType)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="FLOOD">Flood</option>
                <option value="CYCLONE">Cyclone</option>
                <option value="EARTHQUAKE">Earthquake</option>
                <option value="LANDSLIDE">Landslide</option>
                <option value="WILDFIRE">Wildfire</option>
                <option value="OTHER">Other</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Perimeter Radius (m)</label>
              <input
                type="number"
                min="100"
                max="50000"
                required
                value={radiusM}
                onChange={(e) => setRadiusM(e.target.value)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="font-medium text-slate-300">Epicenter Coordinates (Lon, Lat)</label>
              <button
                type="button"
                onClick={handlePickOnMap}
                className="text-[11px] text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                <MapPin className="w-3 h-3" /> Pick on Map
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input
                type="number"
                step="0.00001"
                required
                placeholder="Longitude (e.g. 80.22)"
                value={lon}
                onChange={(e) => setLon(e.target.value)}
                className="bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
              <input
                type="number"
                step="0.00001"
                required
                placeholder="Latitude (e.g. 13.04)"
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                className="bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block font-medium text-slate-300 mb-1">Description (Optional)</label>
            <textarea
              rows={3}
              placeholder="Provide situational context, affected landmarks, or warning notes..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/50 text-white font-medium rounded-xl shadow-lg transition"
          >
            {loading ? 'Declaring Event...' : 'Declare Event'}
          </button>
        </form>
      </div>
    </div>
  );
};
