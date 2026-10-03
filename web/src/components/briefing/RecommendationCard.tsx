import React, { useState } from 'react';
import { ChevronDown, ChevronUp, MapPin, BookOpen, Quote, ShieldAlert } from 'lucide-react';
import { Recommendation, VerificationStatus } from '../../types/api';
import { OriginBadge } from './OriginBadge';
import { VerificationControls } from './VerificationControls';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onVerify: (recId: string, action: VerificationStatus, note?: string) => Promise<void>;
  onFocusCoordinates?: (coords: { lon: number; lat: number }) => void;
}

export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  recommendation,
  onVerify,
  onFocusCoordinates,
}) => {
  const [showCitations, setShowCitations] = useState(false);

  // Extract coordinates from structured_ref if present
  const getCoordinates = (): { lon: number; lat: number } | null => {
    const ref = recommendation.structured_ref;
    if (!ref) return null;
    if (typeof ref.lon === 'number' && typeof ref.lat === 'number') {
      return { lon: ref.lon, lat: ref.lat };
    }
    if (ref.target_location && typeof ref.target_location === 'object') {
      const loc = ref.target_location as { lon?: number; lat?: number };
      if (typeof loc.lon === 'number' && typeof loc.lat === 'number') {
        return { lon: loc.lon, lat: loc.lat };
      }
    }
    return null;
  };

  const coords = getCoordinates();

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-4 shadow-lg hover:border-slate-700 transition-all">
      {/* Top Header: Priority, Title, and Origin Badge */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <span className="flex items-center justify-center w-6 h-6 rounded-md bg-amber-500/20 text-amber-400 font-bold text-xs border border-amber-500/30">
            P{recommendation.priority}
          </span>
          <h4 className="text-sm font-semibold text-slate-100">{recommendation.title}</h4>
        </div>
        <OriginBadge
          origin={recommendation.origin}
          status={recommendation.verification_status}
          verifiedBy={recommendation.verified_by}
          verifiedAt={recommendation.verified_at}
        />
      </div>

      {/* Rationale Body */}
      <p className="text-xs text-slate-300 leading-relaxed mb-3 whitespace-pre-line">
        {recommendation.body}
      </p>

      {/* Meta Bar: Confidence & Locate */}
      <div className="flex items-center justify-between text-xs text-slate-400 py-1.5 px-2 bg-slate-950/60 rounded border border-slate-800/80 mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-slate-400">Confidence:</span>
          {recommendation.confidence !== null && recommendation.confidence !== undefined ? (
            <div className="flex items-center gap-1.5">
              <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${Math.round(recommendation.confidence * 100)}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-emerald-400">
                {Math.round(recommendation.confidence * 100)}%
              </span>
            </div>
          ) : (
            <span className="text-[11px] text-slate-400">Deterministic</span>
          )}
        </div>

        {coords && onFocusCoordinates && (
          <button
            type="button"
            onClick={() => onFocusCoordinates(coords)}
            className="inline-flex items-center gap-1 text-[11px] text-sky-400 hover:text-sky-300 font-medium"
          >
            <MapPin className="w-3 h-3" />
            Locate on Map
          </button>
        )}
      </div>

      {/* Override Note Display if Present */}
      {recommendation.override_note && (
        <div className="text-xs bg-slate-950/80 border border-slate-700/60 rounded p-2 text-slate-300 mb-2 flex items-start gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-slate-300">Note: </span>
            {recommendation.override_note}
          </div>
        </div>
      )}

      {/* Citations Toggle */}
      {recommendation.citations && recommendation.citations.length > 0 && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setShowCitations(!showCitations)}
            className="flex items-center justify-between w-full text-xs text-slate-400 hover:text-slate-200 py-1"
          >
            <span className="inline-flex items-center gap-1.5 font-medium">
              <BookOpen className="w-3.5 h-3.5 text-amber-400" />
              Grounded SOP Citations ({recommendation.citations.length})
            </span>
            {showCitations ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {showCitations && (
            <div className="mt-1.5 space-y-2 pl-2 border-l-2 border-amber-500/40">
              {recommendation.citations.map((c) => (
                <div key={c.id} className="text-xs bg-slate-950/90 p-2.5 rounded border border-slate-800">
                  <div className="flex items-center justify-between font-semibold text-slate-200 mb-1">
                    <span>{c.document_title}</span>
                    {c.relevance_score !== null && c.relevance_score !== undefined && (
                      <span className="text-[10px] text-emerald-400 font-mono">
                        score: {c.relevance_score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  {c.section_path && (
                    <div className="text-[11px] text-slate-400 mb-1">Path: {c.section_path}</div>
                  )}
                  {c.quoted_span && (
                    <div className="text-[11px] text-slate-300 italic flex items-start gap-1 bg-slate-900/60 p-1.5 rounded">
                      <Quote className="w-3 h-3 text-amber-400/80 flex-shrink-0 mt-0.5" />
                      <span>"{c.quoted_span}"</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Verification Controls (Admin only) */}
      <VerificationControls
        recommendationId={recommendation.id}
        currentStatus={recommendation.verification_status}
        onVerify={onVerify}
      />
    </div>
  );
};
