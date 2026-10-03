import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, CheckCircle2, Clock, XCircle, Loader2, Cpu } from 'lucide-react';
import { api } from '../../lib/api';

interface RunTimelineProps {
  eventId?: string;
}

const AGENT_ORDER = [
  { key: 'ASSESSMENT', label: '1. Disaster Assessment', tier: 'Tier A (LLM + RAG)' },
  { key: 'RESCUE_PLANNING', label: '2. Rescue Planning', tier: 'Tier A (LLM + PostGIS)' },
  { key: 'HOSPITAL_RECOMMENDATION', label: '3. Facility Matching', tier: 'Tier B (PostGIS Solver)' },
  { key: 'EVACUATION', label: '4. Evacuation Routing', tier: 'Tier B (A* Router)' },
  { key: 'RESOURCE_COORDINATION', label: '5. Resource Ledger', tier: 'Tier B (Deterministic)' },
  { key: 'CONFLICT_RESOLVER', label: '6. Conflict Resolver', tier: 'Tier B (Solver)' },
  { key: 'SYNTHESIS', label: '7. Briefing Synthesis', tier: 'Tier A (LLM Synthesis)' },
];

export const RunTimeline: React.FC<RunTimelineProps> = ({ eventId }) => {
  const queryClient = useQueryClient();
  const [streamedStatuses, setStreamedStatuses] = useState<Record<string, string>>({});

  const { data: runsData } = useQuery({
    queryKey: ['runs', eventId],
    queryFn: () => (eventId ? api.getEventRuns(eventId) : { items: [], total: 0 }),
    enabled: !!eventId,
    refetchInterval: 3000,
  });

  const latestRun = runsData?.items?.[0];

  // Subscribe to Server-Sent Events (SSE) progress stream for active/latest run
  useEffect(() => {
    if (!latestRun?.id || typeof EventSource === 'undefined') return;

    const es = new EventSource(`/api/v1/runs/${latestRun.id}/stream`);
    es.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.event === 'agent_completed' && payload.agent) {
          setStreamedStatuses((prev) => ({
            ...prev,
            [payload.agent]: payload.status,
          }));
        } else if (payload.event === 'run_completed') {
          queryClient.invalidateQueries({ queryKey: ['runs', eventId] });
          queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] });
          es.close();
        }
      } catch {
        // Ignore malformed SSE lines
      }
    };
    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [latestRun?.id, eventId, queryClient]);

  const triggerMutation = useMutation({
    mutationFn: () => {
      if (!eventId) throw new Error('No event selected');
      return api.triggerRun(eventId, true);
    },
    onSuccess: () => {
      setStreamedStatuses({});
      queryClient.invalidateQueries({ queryKey: ['runs', eventId] });
      queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] });
    },
  });

  const getAgentStatus = (agentKey: string) => {
    if (streamedStatuses[agentKey]) return streamedStatuses[agentKey];
    if (!latestRun) return 'PENDING';
    const output = latestRun.outputs.find((o) => o.agent === agentKey || o.agent.includes(agentKey));
    if (output) return output.status;
    if (latestRun.status === 'RUNNING') return 'RUNNING';
    if (latestRun.status === 'COMPLETED') return 'COMPLETED';
    return 'PENDING';
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-4 shadow-xl">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-sky-400" />
          <h4 className="font-semibold text-xs text-slate-100 uppercase tracking-wider">
            Agent Orchestration Pipeline
          </h4>
        </div>
        <button
          type="button"
          disabled={!eventId || triggerMutation.isPending}
          onClick={() => triggerMutation.mutate()}
          className="inline-flex items-center gap-1.5 px-3 py-1 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 text-white rounded text-xs font-medium transition-colors shadow"
        >
          {triggerMutation.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          Trigger Run
        </button>
      </div>

      {latestRun && (
        <div className="mb-3 text-[11px] text-slate-400 flex items-center justify-between border-b border-slate-800 pb-2">
          <span>
            Run Status:{' '}
            <strong
              className={
                latestRun.status === 'COMPLETED'
                  ? 'text-emerald-400'
                  : latestRun.status === 'RUNNING'
                  ? 'text-amber-400 animate-pulse'
                  : 'text-slate-300'
              }
            >
              {latestRun.status}
            </strong>
          </span>
          {latestRun.total_latency_ms && (
            <span className="font-mono">{latestRun.total_latency_ms} ms</span>
          )}
        </div>
      )}

      {/* Agents Timeline Steps */}
      <div className="space-y-2">
        {AGENT_ORDER.map(({ key, label, tier }) => {
          const status = getAgentStatus(key);
          return (
            <div
              key={key}
              className="flex items-center justify-between p-2 rounded bg-slate-950/60 border border-slate-800/80 text-xs"
            >
              <div>
                <div className="font-medium text-slate-200">{label}</div>
                <div className="text-[10px] text-slate-400">{tier}</div>
              </div>

              <div>
                {(status === 'COMPLETED' || status === 'SUCCESS') && (
                  <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                    <CheckCircle2 className="w-4 h-4" /> Done
                  </span>
                )}
                {status === 'RUNNING' && (
                  <span className="flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                    <Loader2 className="w-4 h-4 animate-spin" /> Running
                  </span>
                )}
                {(status === 'FAILED' || status === 'TIMEOUT' || status === 'INSUFFICIENT_EVIDENCE') && (
                  <span className="flex items-center gap-1 text-[11px] text-rose-400 font-medium">
                    <XCircle className="w-4 h-4" /> {status === 'TIMEOUT' ? 'Timeout' : 'Failed'}
                  </span>
                )}
                {status === 'PENDING' && (
                  <span className="flex items-center gap-1 text-[11px] text-slate-400">
                    <Clock className="w-3.5 h-3.5" /> Queued
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
