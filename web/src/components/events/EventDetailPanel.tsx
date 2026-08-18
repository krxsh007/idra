import React from 'react';
import {
  ShieldAlert,
  Clock,
  Radio,
  FileText,
  AlertTriangle,
  Plus,
} from 'lucide-react';
import { DisasterEvent, HazardZone, IncidentReport } from '../../types/api';

interface EventDetailPanelProps {
  event: DisasterEvent | null;
  hazardZones: HazardZone[];
  reports: IncidentReport[];
  onAddHazardZone: () => void;
  onOpenReportModal: () => void;
}

export const EventDetailPanel: React.FC<EventDetailPanelProps> = ({
  event,
  hazardZones,
  reports,
  onAddHazardZone,
  onOpenReportModal,
}) => {
  if (!event) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center text-slate-500 bg-slate-900/40 border-l border-slate-800">
        <ShieldAlert className="w-10 h-10 mb-3 text-slate-600" />
        <p className="text-sm font-medium text-slate-400">No Disaster Event Selected</p>
        <p className="text-xs text-slate-500 mt-1 max-w-xs">
          Select an active disaster event from the top navigation to view situation updates, hazard zones, and incident reports.
        </p>
      </div>
    );
  }

  const declaredDate = new Date(event.declared_at).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className="h-full flex flex-col bg-slate-900 border-l border-slate-800 w-80 lg:w-96 text-xs text-slate-300">
      {/* Event Header */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/90">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase bg-red-950 text-red-300 border border-red-800/80">
            {event.disaster_type}
          </span>
          <span
            className={`px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase ${
              event.status === 'ACTIVE'
                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                : 'bg-slate-800 text-slate-400 border border-slate-700'
            }`}
          >
            {event.status}
          </span>
        </div>

        <h2 className="text-base font-bold text-white tracking-tight leading-snug">
          {event.name}
        </h2>

        {event.description && (
          <p className="mt-1 text-slate-400 text-[11px] line-clamp-2">
            {event.description}
          </p>
        )}

        <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
          <div className="p-2 bg-slate-800/60 rounded-lg border border-slate-700/40 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-blue-400" />
            <span>{declaredDate}</span>
          </div>
          <div className="p-2 bg-slate-800/60 rounded-lg border border-slate-700/40 flex items-center gap-1.5">
            <Radio className="w-3.5 h-3.5 text-blue-400" />
            <span>{event.radius_m}m radius</span>
          </div>
        </div>
      </div>

      {/* Tabs & Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Hazard Zones Section */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
              <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
              <span>Hazard Zones ({hazardZones.length})</span>
            </div>
            <button
              onClick={onAddHazardZone}
              className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-0.5"
            >
              <Plus className="w-3 h-3" /> Add Zone
            </button>
          </div>

          {hazardZones.length === 0 ? (
            <div className="p-3 bg-slate-800/30 rounded-lg border border-slate-800 text-center text-slate-500 text-[11px]">
              No active hazard polygons defined.
            </div>
          ) : (
            <div className="space-y-2">
              {hazardZones.map((hz) => (
                <div
                  key={hz.id}
                  className="p-2.5 bg-slate-800/50 rounded-lg border border-slate-700/60 space-y-1 hover:border-slate-600 transition"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200">{hz.label}</span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${
                        hz.severity === 'SEVERE'
                          ? 'bg-red-900/60 text-red-300 border border-red-800'
                          : hz.severity === 'HIGH'
                          ? 'bg-orange-900/60 text-orange-300 border border-orange-800'
                          : 'bg-yellow-900/60 text-yellow-300 border border-yellow-800'
                      }`}
                    >
                      {hz.severity}
                    </span>
                  </div>
                  {hz.is_impassable && (
                    <div className="text-[10px] text-red-400 font-medium">
                      ⛔ Road Access Impassable
                    </div>
                  )}
                  {hz.source_note && (
                    <div className="text-[10px] text-slate-400">{hz.source_note}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Incident Reports Section */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
              <FileText className="w-3.5 h-3.5 text-amber-400" />
              <span>Incident Reports ({reports.length})</span>
            </div>
            <button
              onClick={onOpenReportModal}
              className="text-[10px] text-amber-400 hover:text-amber-300 flex items-center gap-0.5"
            >
              <Plus className="w-3 h-3" /> Submit
            </button>
          </div>

          {reports.length === 0 ? (
            <div className="p-3 bg-slate-800/30 rounded-lg border border-slate-800 text-center text-slate-500 text-[11px]">
              No incident reports received yet.
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map((r) => (
                <div
                  key={r.id}
                  className="p-2.5 bg-slate-800/50 rounded-lg border border-slate-700/60 space-y-1.5 hover:border-slate-600 transition"
                >
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-semibold text-slate-300">{r.source} Report</span>
                    <span className="text-[10px] text-slate-500">
                      {new Date(r.reported_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed line-clamp-3">
                    {r.body}
                  </p>
                  <div className="flex items-center gap-2 text-[10px]">
                    {r.casualties_reported && (
                      <span className="text-rose-400 font-bold flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> Casualties
                      </span>
                    )}
                    {r.people_affected && (
                      <span className="text-slate-400">
                        {r.people_affected} affected
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
