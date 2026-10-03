import React from 'react';
import { Database, Activity } from 'lucide-react';
import { Provenance } from '../../types/api';

interface ProvenanceTagProps {
  provenance: Provenance | string;
  className?: string;
  showReal?: boolean;
}

export const ProvenanceTag: React.FC<ProvenanceTagProps> = ({
  provenance,
  className = '',
  showReal = false,
}) => {
  if (provenance === 'SIMULATED' || provenance === 'SYNTHETIC') {
    return (
      <span
        title="Computed from calibrated simulation or model estimate"
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/80 text-amber-300 border border-amber-800/50 ${className}`}
      >
        <Activity className="w-3 h-3 text-amber-400" />
        simulated capacity
      </span>
    );
  }

  if (showReal) {
    return (
      <span
        title="Verified database ground truth"
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700 ${className}`}
      >
        <Database className="w-3 h-3 text-slate-400" />
        verified ground truth
      </span>
    );
  }

  return null;
};
