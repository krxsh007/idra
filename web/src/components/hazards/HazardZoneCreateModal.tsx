import React, { useState } from 'react';
import { X, ShieldAlert, AlertCircle } from 'lucide-react';
import { api } from '../../lib/api';
import { DisasterType, SeverityLevel } from '../../types/api';

interface HazardZoneCreateModalProps {
  isOpen: boolean;
  eventId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export const HazardZoneCreateModal: React.FC<HazardZoneCreateModalProps> = ({
  isOpen,
  eventId,
  onClose,
  onSuccess,
}) => {
  const [label, setLabel] = useState('');
  const [hazardType, setHazardType] = useState<DisasterType>('FLOOD');
  const [severity, setSeverity] = useState<SeverityLevel>('HIGH');
  const [isImpassable, setIsImpassable] = useState(false);
  const [coordsText, setCoordsText] = useState(
    '80.20, 13.00\n80.25, 13.00\n80.25, 13.05\n80.20, 13.05\n80.20, 13.00'
  );
  const [sourceNote, setSourceNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Parse coordinates
      const lines = coordsText.trim().split('\n');
      const ring: number[][] = [];
      for (const line of lines) {
        const parts = line.split(',').map((p) => parseFloat(p.trim()));
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
          ring.push([parts[0], parts[1]]);
        }
      }

      if (ring.length < 4) {
        throw new Error('Polygon must contain at least 4 coordinate pairs (lon, lat).');
      }

      await api.createHazardZone({
        event_id: eventId,
        label,
        hazard_type: hazardType,
        severity,
        is_impassable: isImpassable,
        geometry: {
          type: 'Polygon',
          coordinates: [ring],
        },
        source_note: sourceNote || undefined,
      });

      setLoading(false);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setLoading(false);
      setError(err instanceof Error ? err.message : 'Failed to create hazard zone');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl relative text-xs">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-6">
          <div className="p-2.5 bg-red-600/20 text-red-400 rounded-xl border border-red-500/30">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Define Hazard Zone Polygon</h2>
            <p className="text-[11px] text-slate-400">Add spatial danger perimeter and road blockage boundaries (Admin)</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-950/60 border border-red-800/80 rounded-xl text-red-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block font-medium text-slate-300 mb-1">Zone Label</label>
            <input
              type="text"
              required
              placeholder="e.g. Adyar River Basin Inundation"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Hazard Type</label>
              <select
                value={hazardType}
                onChange={(e) => setHazardType(e.target.value as DisasterType)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="FLOOD">Flood</option>
                <option value="CYCLONE">Cyclone</option>
                <option value="EARTHQUAKE">Earthquake</option>
                <option value="LANDSLIDE">Landslide</option>
                <option value="WILDFIRE">Wildfire</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Severity Level</label>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as SeverityLevel)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="SEVERE">Severe (Red)</option>
                <option value="HIGH">High (Orange)</option>
                <option value="MODERATE">Moderate (Yellow)</option>
                <option value="LOW">Low (Cyan)</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2 p-2.5 bg-slate-800/50 rounded-xl border border-slate-700/60">
            <input
              type="checkbox"
              id="impassable"
              checked={isImpassable}
              onChange={(e) => setIsImpassable(e.target.checked)}
              className="rounded bg-slate-700 border-slate-600 text-red-600 focus:ring-0"
            />
            <label htmlFor="impassable" className="font-semibold text-slate-200 cursor-pointer">
              Road Access Impassable (Blocks traffic routing in this perimeter)
            </label>
          </div>

          <div>
            <label className="block font-medium text-slate-300 mb-1">
              Polygon Coordinates (lon, lat - one per line, closed loop)
            </label>
            <textarea
              rows={4}
              required
              value={coordsText}
              onChange={(e) => setCoordsText(e.target.value)}
              className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white font-mono text-[11px] focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block font-medium text-slate-300 mb-1">Source Note (Optional)</label>
            <input
              type="text"
              placeholder="e.g. Field verification team alpha"
              value={sourceNote}
              onChange={(e) => setSourceNote(e.target.value)}
              className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-red-600 hover:bg-red-500 disabled:bg-red-800/50 text-white font-medium rounded-xl shadow-lg transition"
          >
            {loading ? 'Creating Hazard Zone...' : 'Create Hazard Zone'}
          </button>
        </form>
      </div>
    </div>
  );
};
