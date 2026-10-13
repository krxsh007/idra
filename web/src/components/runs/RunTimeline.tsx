import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, CheckCircle2, Clock, XCircle, Loader2, Cpu, ChevronDown, ChevronRight } from 'lucide-react';
import { api } from '../../lib/api';
import { summarizeAgent } from './agentSummaries';

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
  // Live statuses from the SSE stream, tagged with the run they belong to so a previous run's
  // completions never show as "Done" on a run that has just started.
  const [streamed, setStreamed] = useState<{ runId: string | null; statuses: Record<string, string> }>({
    runId: null,
    statuses: {},
  });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

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
          setStreamed((prev) => ({
            runId: latestRun.id,
            statuses: {
              ...(prev.runId === latestRun.id ? prev.statuses : {}),
              [payload.agent]: payload.status,
            },
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
    onMutate: () => {
      setStreamed({ runId: null, statuses: {} });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs', eventId] });
      queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] });
    },
  });

  const findOutput = (agentKey: string) =>
    latestRun?.outputs.find((o) => o.agent === agentKey || o.agent.includes(agentKey));
  const synthesisOutput = findOutput('SYNTHESIS');

  // The conflict resolver has no output of its own; it has run once resource allocation is done.
  const hasFinished = (agentKey: string) =>
    agentKey === 'CONFLICT_RESOLVER' ? !!findOutput('RESOURCE_COORDINATION') : !!findOutput(agentKey);
  const firstUnfinished = AGENT_ORDER.find(({ key }) => !hasFinished(key))?.key;

  const getAgentStatus = (agentKey: string) => {
    if (!latestRun) return 'PENDING';
    const streamedStatus =
      streamed.runId === latestRun.id
        ? Object.entries(streamed.statuses).find(([agent]) => agent.includes(agentKey))?.[1]
        : undefined;
    if (streamedStatus) return streamedStatus;
    const output = findOutput(agentKey);
    if (output) return output.status;
    if (latestRun.status === 'RUNNING') {
      if (agentKey === 'CONFLICT_RESOLVER' && hasFinished(agentKey)) return 'COMPLETED';
      return agentKey === firstUnfinished ? 'RUNNING' : 'PENDING';
    }
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
          const isDone = status === 'COMPLETED' || status === 'SUCCESS';
          const isFailed = status === 'FAILED' || status === 'TIMEOUT' || status === 'INSUFFICIENT_EVIDENCE';
          const summary = isDone || isFailed ? summarizeAgent(key, findOutput(key), synthesisOutput) : null;
          const isOpen = !!expanded[key];
          return (
            <div
              key={key}
              className="p-2 rounded bg-slate-950/60 border border-slate-800/80 text-xs"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-slate-200">{label}</div>
                  <div className="text-[10px] text-slate-400">{tier}</div>
                </div>

                <div>
                  {isDone && (
                    <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                      <CheckCircle2 className="w-4 h-4" /> Done
                    </span>
                  )}
                  {status === 'RUNNING' && (
                    <span className="flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                      <Loader2 className="w-4 h-4 animate-spin" /> Running
                    </span>
                  )}
                  {isFailed && (
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

              {/* What the agent found */}
              {summary && (
                <div className="mt-1.5 pt-1.5 border-t border-slate-800/80">
                  <p className={`text-[11px] leading-snug ${isFailed ? 'text-rose-300' : 'text-slate-300'}`}>
                    {summary.headline}
                  </p>
                  {summary.details.length > 0 && (
                    <>
                      <button
                        type="button"
                        onClick={() => setExpanded((prev) => ({ ...prev, [key]: !prev[key] }))}
                        className="mt-1 inline-flex items-center gap-0.5 text-[10px] text-sky-400 hover:text-sky-300"
                      >
                        {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        {isOpen ? 'Hide details' : 'Details'}
                      </button>
                      {isOpen && (
                        <ul className="mt-1 space-y-0.5 text-[10.5px] leading-snug text-slate-400 list-disc pl-4">
                          {summary.details.map((d, i) => (
                            <li key={i}>{d}</li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
