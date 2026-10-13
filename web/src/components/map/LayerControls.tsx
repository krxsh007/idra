import React from 'react';
import { Layers, ShieldAlert, Eye, EyeOff, MapPin, Radio, Building2, Route } from 'lucide-react';
import { useMapStore } from '../../stores/mapStore';

export const LayerControls: React.FC = () => {
  const { showBBox, showHazards, showReports, showFacilities, showRoutes, toggleLayer } =
    useMapStore();

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-xl p-3 shadow-xl text-xs space-y-3 w-56">
      <div className="flex items-center gap-2 font-semibold text-slate-200 border-b border-slate-800 pb-2">
        <Layers className="w-4 h-4 text-blue-400" />
        <span>Map Layers</span>
      </div>

      <div className="space-y-1.5">
        <button
          onClick={() => toggleLayer('showBBox')}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-all ${
            showBBox
              ? 'bg-blue-950/40 border-blue-800/60 text-blue-300'
              : 'bg-slate-800/40 border-slate-800 text-slate-500 hover:text-slate-400'
          }`}
        >
          <div className="flex items-center gap-2">
            <Radio className="w-3.5 h-3.5 text-blue-400" />
            <span>Study Area (BBox)</span>
          </div>
          {showBBox ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>

        <button
          onClick={() => toggleLayer('showHazards')}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-all ${
            showHazards
              ? 'bg-red-950/40 border-red-800/60 text-red-300'
              : 'bg-slate-800/40 border-slate-800 text-slate-500 hover:text-slate-400'
          }`}
        >
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
            <span>Hazard Polygons</span>
          </div>
          {showHazards ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>

        <button
          onClick={() => toggleLayer('showReports')}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-all ${
            showReports
              ? 'bg-amber-950/40 border-amber-800/60 text-amber-300'
              : 'bg-slate-800/40 border-slate-800 text-slate-500 hover:text-slate-400'
          }`}
        >
          <div className="flex items-center gap-2">
            <MapPin className="w-3.5 h-3.5 text-amber-400" />
            <span>Incident Reports</span>
          </div>
          {showReports ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>

        <button
          onClick={() => toggleLayer('showFacilities')}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-all ${
            showFacilities
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
              : 'bg-slate-800/40 border-slate-800 text-slate-500 hover:text-slate-400'
          }`}
        >
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Facilities (Hosp/Shelt)</span>
          </div>
          {showFacilities ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>

        <button
          onClick={() => toggleLayer('showRoutes')}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-all ${
            showRoutes
              ? 'bg-sky-950/40 border-sky-800/60 text-sky-300'
              : 'bg-slate-800/40 border-slate-800 text-slate-500 hover:text-slate-400'
          }`}
        >
          <div className="flex items-center gap-2">
            <Route className="w-3.5 h-3.5 text-sky-400" />
            <span>Evacuation Routes</span>
          </div>
          {showRoutes ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>
      </div>

      <div className="border-t border-slate-800/80 pt-2 space-y-1 text-[11px] text-slate-400">
        <div className="font-medium text-slate-300 mb-1">Map Legend</div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-sm bg-red-500/80 border border-red-400" />
          <span>Severe Hazard</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-sm bg-orange-500/80 border border-orange-400" />
          <span>High Hazard</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500 ring-2 ring-red-400/40" />
          <span>Event Epicenter</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-blue-600 border border-white flex items-center justify-center text-[7px] font-bold text-white">
            H
          </div>
          <span>Hospital (Blue)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-green-600 border border-white flex items-center justify-center text-[7px] font-bold text-white">
            S
          </div>
          <span>Shelter (Green)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-0.5 rounded bg-blue-500" />
          <span>Route to Hospital</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-0.5 rounded bg-green-500" />
          <span>Route to Shelter</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-amber-400 border border-slate-950" />
          <span>Rescue Zone (route start)</span>
        </div>
      </div>
    </div>
  );
};
