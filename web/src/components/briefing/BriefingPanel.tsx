import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ClipboardList, Filter, AlertTriangle } from 'lucide-react';
import { api } from '../../lib/api';
import { RecommendationCard } from './RecommendationCard';
import { VerificationStatus } from '../../types/api';

interface BriefingPanelProps {
  eventId?: string;
  onFocusCoordinates?: (coords: { lon: number; lat: number }) => void;
}

export const BriefingPanel: React.FC<BriefingPanelProps> = ({
  eventId,
  onFocusCoordinates,
}) => {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<VerificationStatus | 'ALL'>('ALL');

  const { data, isLoading, error } = useQuery({
    queryKey: ['recommendations', eventId, statusFilter],
    queryFn: () =>
      api.getRecommendations(
        eventId,
        statusFilter === 'ALL' ? undefined : statusFilter
      ),
    enabled: !!eventId,
    refetchInterval: 5000,
  });

  const verifyMutation = useMutation({
    mutationFn: ({
      recId,
      action,
      note,
    }: {
      recId: string;
      action: VerificationStatus;
      note?: string;
    }) => api.verifyRecommendation(recId, { action, note }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] });
    },
  });

  const handleVerify = async (
    recId: string,
    action: VerificationStatus,
    note?: string
  ): Promise<void> => {
    await verifyMutation.mutateAsync({ recId, action, note });
  };

  const recommendations = data?.items || [];

  return (
    <div className="flex flex-col h-full bg-slate-950/95 text-slate-100 w-full overflow-hidden">
      {/* Top Header */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/60">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-amber-400" />
            <h3 className="font-semibold text-sm tracking-wide">Prioritized Briefing</h3>
          </div>
          <span className="text-xs font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
            {recommendations.length} Actions
          </span>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center gap-1 text-xs">
          <Filter className="w-3.5 h-3.5 text-slate-400 mr-1" />
          {(['ALL', 'PENDING', 'VERIFIED'] as const).map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => setStatusFilter(filter)}
              className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                statusFilter === filter
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>

      {/* Content List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isLoading && (
          <div className="text-center py-8 text-xs text-slate-400 animate-pulse">
            Loading prioritized recommendations...
          </div>
        )}

        {error && (
          <div className="p-3 bg-rose-950/50 border border-rose-800/60 rounded text-xs text-rose-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>Failed to load recommendations.</span>
          </div>
        )}

        {!isLoading && recommendations.length === 0 && (
          <div className="text-center py-12 px-4 text-xs text-slate-400">
            <ClipboardList className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="font-medium text-slate-300">No recommendations generated yet</p>
            <p className="text-slate-400 mt-1">
              Trigger a multi-agent run to generate prioritized rescue and shelter proposals.
            </p>
          </div>
        )}

        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.id}
            recommendation={rec}
            onVerify={handleVerify}
            onFocusCoordinates={onFocusCoordinates}
          />
        ))}
      </div>
    </div>
  );
};
