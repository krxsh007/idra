import React, { useState } from 'react';
import { X, FilePlus2, AlertCircle, MapPin, AlertTriangle } from 'lucide-react';
import { api } from '../../lib/api';
import { EpicenterPoint, IncidentReport, ReportSource } from '../../types/api';
import { useAuthStore } from '../../stores/authStore';

interface ReportSubmissionModalProps {
  isOpen: boolean;
  eventId?: string | null;
  onClose: () => void;
  onSuccess: (report: IncidentReport) => void;
  onStartLocationPick: (onPick: (coords: EpicenterPoint) => void) => void;
}

export const ReportSubmissionModal: React.FC<ReportSubmissionModalProps> = ({
  isOpen,
  eventId,
  onClose,
  onSuccess,
  onStartLocationPick,
}) => {
  const { user } = useAuthStore();

  const [body, setBody] = useState('');
  const [lon, setLon] = useState('80.225');
  const [lat, setLat] = useState('13.05');
  const [source, setSource] = useState<ReportSource>(
    user?.role === 'RESPONDER' ? 'RESPONDER' : 'CITIZEN'
  );
  const [reporterName, setReporterName] = useState(user?.full_name || '');
  const [reporterPhone, setReporterPhone] = useState('');
  const [casualtiesReported, setCasualtiesReported] = useState(false);
  const [peopleAffected, setPeopleAffected] = useState('');
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
      const created = await api.submitReport({
        event_id: eventId || undefined,
        source,
        reporter_name: reporterName || undefined,
        reporter_phone: reporterPhone || undefined,
        body,
        location: { lon: parseFloat(lon), lat: parseFloat(lat) },
        casualties_reported: casualtiesReported,
        people_affected: peopleAffected ? parseInt(peopleAffected, 10) : undefined,
      });

      setLoading(false);
      onSuccess(created);
      onClose();
    } catch (err: unknown) {
      setLoading(false);
      setError(err instanceof Error ? err.message : 'Failed to submit report');
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
          <div className="p-2.5 bg-amber-600/20 text-amber-400 rounded-xl border border-amber-500/30">
            <FilePlus2 className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">Submit Incident Report</h2>
            <p className="text-[11px] text-slate-400">
              Provide ground observations, road obstructions, or casualty alerts
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-950/60 border border-red-800/80 rounded-xl text-xs text-red-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Report Source</label>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value as ReportSource)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="CITIZEN">Citizen Report</option>
                <option value="RESPONDER">Field Responder</option>
                <option value="SENSOR">Sensor / Gauge</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">People Affected</label>
              <input
                type="number"
                min="0"
                placeholder="Optional count"
                value={peopleAffected}
                onChange={(e) => setPeopleAffected(e.target.value)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block font-medium text-slate-300 mb-1">
              Incident Description (min 5 characters)
            </label>
            <textarea
              rows={3}
              required
              minLength={5}
              maxLength={4000}
              placeholder="Describe observed conditions, water level, building damage, or stranded citizens..."
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="font-medium text-slate-300">Incident Location (Lon, Lat)</label>
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

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Reporter Name</label>
              <input
                type="text"
                placeholder="Optional"
                value={reporterName}
                onChange={(e) => setReporterName(e.target.value)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1">Reporter Phone</label>
              <input
                type="tel"
                placeholder="Optional"
                value={reporterPhone}
                onChange={(e) => setReporterPhone(e.target.value)}
                className="w-full bg-slate-800/70 border border-slate-700 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="pt-1">
            <div className="flex items-center gap-2 p-2.5 bg-slate-800/50 rounded-xl border border-slate-700/60">
              <input
                type="checkbox"
                id="casualties"
                checked={casualtiesReported}
                onChange={(e) => setCasualtiesReported(e.target.checked)}
                className="rounded bg-slate-700 border-slate-600 text-rose-600 focus:ring-0"
              />
              <label
                htmlFor="casualties"
                className="font-semibold text-rose-300 cursor-pointer flex items-center gap-1"
              >
                <AlertTriangle className="w-3.5 h-3.5" /> Casualties Reported
              </label>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-amber-600 hover:bg-amber-500 disabled:bg-amber-800/50 text-white font-medium rounded-xl shadow-lg transition"
          >
            {loading ? 'Submitting Report...' : 'Submit Incident Report'}
          </button>
        </form>
      </div>
    </div>
  );
};
