import React from 'react';
import { Sparkles, CheckCircle, RefreshCw, XCircle, Cpu } from 'lucide-react';
import { Origin, VerificationStatus } from '../../types/api';

interface OriginBadgeProps {
  origin: Origin;
  status: VerificationStatus;
  verifiedBy?: string | null;
  verifiedAt?: string | null;
  className?: string;
}

export const OriginBadge: React.FC<OriginBadgeProps> = ({
  origin,
  status,
  verifiedBy,
  verifiedAt,
  className = '',
}) => {
  if (status === 'VERIFIED') {
    const timeFormatted = verifiedAt ? new Date(verifiedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    return (
      <span
        title={verifiedBy ? `Verified by ${verifiedBy} at ${verifiedAt}` : 'Verified recommendation'}
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950 text-emerald-300 border border-emerald-700/50 ${className}`}
      >
        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
        Verified {timeFormatted ? `at ${timeFormatted}` : ''}
      </span>
    );
  }

  if (status === 'OVERRIDDEN') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-600 ${className}`}
      >
        <RefreshCw className="w-3 h-3 text-slate-400" />
        Overridden
      </span>
    );
  }

  if (status === 'REJECTED') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-950 text-red-300 line-through border border-red-800/60 ${className}`}
      >
        <XCircle className="w-3.5 h-3.5 text-red-400" />
        Rejected
      </span>
    );
  }

  // PENDING state
  if (origin === 'AI_GENERATED') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-950 text-amber-300 border border-amber-700/60 animate-pulse ${className}`}
      >
        <Sparkles className="w-3.5 h-3.5 text-amber-400" />
        AI-generated • Pending verification
      </span>
    );
  }

  if (origin === 'DETERMINISTIC_COMPUTATION') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-sky-950 text-sky-300 border border-sky-700/60 ${className}`}
      >
        <Cpu className="w-3.5 h-3.5 text-sky-400" />
        Deterministic computation • Pending verification
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-300 ${className}`}
    >
      Pending verification
    </span>
  );
};
