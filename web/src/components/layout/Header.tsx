import React from 'react';
import {
  ShieldAlert,
  PlusCircle,
  FilePlus2,
  LogIn,
  LogOut,
  User as UserIcon,
} from 'lucide-react';
import { DisasterEvent } from '../../types/api';
import { useAuthStore } from '../../stores/authStore';

interface HeaderProps {
  events: DisasterEvent[];
  activeEvent: DisasterEvent | null;
  onSelectEvent: (event: DisasterEvent | null) => void;
  onOpenLogin: () => void;
  onOpenNewEvent: () => void;
  onOpenSubmitReport: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  events,
  activeEvent,
  onSelectEvent,
  onOpenLogin,
  onOpenNewEvent,
  onOpenSubmitReport,
}) => {
  const { user, isAuthenticated, logout, hasRole } = useAuthStore();

  return (
    <header className="bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-6 py-3.5 flex items-center justify-between shadow-md">
      {/* Brand & Active Event Selector */}
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/30 shadow-inner">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-white tracking-tight">IDRA</span>
              <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-md bg-blue-950 text-blue-300 border border-blue-800/60">
                Chennai Core
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Decision Support Platform</p>
          </div>
        </div>

        {/* Event Selector Dropdown */}
        <div className="hidden md:flex items-center space-x-2 pl-4 border-l border-slate-800">
          <label className="text-xs font-medium text-slate-400">Active Event:</label>
          <select
            value={activeEvent?.id || ''}
            onChange={(e) => {
              const selected = events.find((ev) => ev.id === e.target.value) || null;
              onSelectEvent(selected);
            }}
            className="bg-slate-800/80 border border-slate-700 text-white text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          >
            {events.length === 0 ? (
              <option value="">No Active Events Found</option>
            ) : (
              <>
                <option value="">-- Select Active Event --</option>
                {events.map((ev) => (
                  <option key={ev.id} value={ev.id}>
                    {ev.name} ({ev.disaster_type} - {ev.status})
                  </option>
                ))}
              </>
            )}
          </select>
        </div>
      </div>

      {/* Action Buttons & User Menu */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenSubmitReport}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 rounded-lg text-xs font-medium transition shadow-sm"
        >
          <FilePlus2 className="w-3.5 h-3.5" />
          <span>Report Incident</span>
        </button>

        {hasRole('ADMIN') && (
          <button
            onClick={onOpenNewEvent}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition shadow-sm"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>Declare Event</span>
          </button>
        )}

        {isAuthenticated && user ? (
          <div className="flex items-center space-x-2 pl-3 border-l border-slate-800">
            <div className="flex items-center gap-1.5 bg-slate-800/80 border border-slate-700/80 px-2.5 py-1 rounded-lg">
              <UserIcon className="w-3.5 h-3.5 text-blue-400" />
              <div className="text-left">
                <span className="text-xs font-semibold text-slate-200 block leading-tight">
                  {user.full_name || user.email.split('@')[0]}
                </span>
                <span className="text-[10px] font-bold text-blue-400 uppercase leading-none">
                  {user.role}
                </span>
              </div>
            </div>
            <button
              onClick={logout}
              title="Sign Out"
              className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenLogin}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-medium transition"
          >
            <LogIn className="w-3.5 h-3.5 text-slate-400" />
            <span>Sign In</span>
          </button>
        )}
      </div>
    </header>
  );
};
