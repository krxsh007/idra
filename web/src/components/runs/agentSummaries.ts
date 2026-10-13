import { AgentOutput } from '../../types/api';

export interface AgentSummary {
  headline: string;
  details: string[];
}

// Payloads arrive as untyped JSON; read fields defensively so a schema change never breaks the timeline.
type Payload = Record<string, unknown>;
const list = (p: Payload, key: string): Payload[] => (Array.isArray(p[key]) ? (p[key] as Payload[]) : []);
const strings = (p: Payload, key: string): string[] =>
  Array.isArray(p[key]) ? (p[key] as unknown[]).filter((x): x is string => typeof x === 'string') : [];
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const km = (m: unknown) => `${((num(m) ?? 0) / 1000).toFixed(1)} km`;
const mins = (s: unknown) => `~${Math.max(1, Math.round((num(s) ?? 0) / 60))} min`;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

const summarizeAssessment = (p: Payload): AgentSummary => {
  const parts = [`Severity ${p.severity ?? 'unknown'}`];
  const affected = num(p.estimated_people_affected);
  if (affected !== null) parts.push(`~${affected.toLocaleString()} people affected`);
  const confidence = num(p.confidence);
  if (confidence !== null) parts.push(`${Math.round(confidence * 100)}% confidence`);
  const details = strings(p, 'key_factors');
  if (p.casualties_reported) details.push('Casualties reported in incident data');
  if (p.evacuation_recommended) details.push('Evacuation recommended');
  details.push(`Grounded in ${plural(list(p, 'citations').length, 'cited source')}`);
  return { headline: parts.join(' · '), details };
};

const summarizeRescuePlanning = (p: Payload): AgentSummary => {
  const zones = list(p, 'prioritized_zones');
  const top = zones[0];
  const headline = top
    ? `${plural(zones.length, 'rescue zone')} prioritised · first: ${top.zone_label} (~${num(top.people_estimate) ?? '?'} people)`
    : 'No rescue zones identified';
  const details = [
    ...zones.map((z) => `P${z.priority} ${z.zone_label}: ${z.accessibility}, ~${num(z.people_estimate) ?? '?'} people`),
    ...strings(p, 'operation_sequence').slice(0, 3).map((step, i) => `Step ${i + 1}: ${step}`),
  ];
  return { headline, details };
};

const summarizeFacilities = (p: Payload): AgentSummary => {
  const hospital = list(p, 'recommended_hospitals')[0];
  const shelter = list(p, 'recommended_shelters')[0];
  const parts: string[] = [];
  if (hospital) parts.push(`Hospital: ${hospital.name} (${km(hospital.distance_m)})`);
  if (shelter) parts.push(`Shelter: ${shelter.name} (${km(shelter.distance_m)})`);
  const details = [
    `${num(p.total_hospital_capacity_available) ?? 0} hospital beds and ${num(p.total_shelter_capacity_available) ?? 0} shelter places available`,
  ];
  // The agent states which facilities it skipped for being inside a hazard zone.
  const excluded = typeof p.rationale === 'string' ? p.rationale.match(/Excluded .*$/)?.[0] : undefined;
  details.push(excluded ?? 'No candidate facility lies inside a hazard zone');
  return { headline: parts.join(' · ') || 'No operational facilities with free capacity found', details };
};

const summarizeRouting = (p: Payload): AgentSummary => {
  const routes = list(p, 'routes');
  const avoided = routes.filter((r) => r.hazard_avoided).length;
  const unreachable = strings(p, 'unreachable_locations');
  const headline =
    `${plural(routes.length, 'route')} on real roads · ${avoided} avoid all other hazard zones` +
    (unreachable.length ? ` · ${unreachable.length} unreachable` : '');
  const details = routes.map((r) => {
    const notes: string[] = [];
    if (r.starts_in_hazard) notes.push('starts inside a hazard zone, shortest way out');
    if (r.traverses_hazard) notes.push('passes through another hazard zone');
    return `→ ${r.destination_name}: ${km(r.distance_m)}, ${mins(r.duration_s)}${notes.length ? ` (${notes.join('; ')})` : ''}`;
  });
  details.push(...unreachable.map((u) => `Unreachable: ${u}`));
  return { headline, details };
};

const summarizeResources = (p: Payload): AgentSummary => {
  const allocations = list(p, 'allocations');
  const shortages = strings(p, 'shortages_identified');
  const headline =
    `${num(p.total_allocated) ?? 0} units in ${plural(allocations.length, 'allocation')}` +
    (shortages.length ? ` · ${plural(shortages.length, 'shortfall')}` : ' · no shortfalls');
  const details = [
    ...allocations
      .slice(0, 4)
      .map((a) => `${a.quantity} × ${String(a.label ?? a.resource_kind)} → ${a.target_zone_label ?? 'zone'}`),
    ...shortages,
  ];
  return { headline, details };
};

const summarizeConflicts = (synthesis: Payload | undefined): AgentSummary | null => {
  if (!synthesis) return null;
  const conflicts = strings(synthesis, 'conflicts_noted');
  return {
    headline: conflicts.length ? `${plural(conflicts.length, 'conflict')} resolved` : 'No conflicts between agent plans',
    details: conflicts,
  };
};

const summarizeSynthesis = (p: Payload): AgentSummary => {
  const summary = typeof p.executive_summary === 'string' ? p.executive_summary : '';
  return {
    headline: `${plural(list(p, 'recommendations').length, 'prioritised action')} in the briefing`,
    details: summary ? [summary] : [],
  };
};

const FAILURE_EXPLANATIONS: Record<string, string> = {
  LLM_UNAVAILABLE:
    'AI model unavailable (provider overloaded or unreachable). The pipeline continued on a rule-based baseline and the run is flagged for human review.',
  AGENT_TIMEOUT: 'Timed out before finishing; later stages continued with the data available.',
  LLM_INVALID_OUTPUT: 'The AI model returned invalid output twice, so its answer was discarded.',
};

/** One-line headline plus expandable details describing what an agent found. */
export const summarizeAgent = (
  agentKey: string,
  output: AgentOutput | undefined,
  synthesisOutput: AgentOutput | undefined
): AgentSummary | null => {
  if (agentKey === 'CONFLICT_RESOLVER') {
    // The resolver runs inside the pipeline; its decisions are reported by the synthesis stage.
    return summarizeConflicts(synthesisOutput?.payload ?? undefined);
  }
  if (!output) return null;
  if (output.error_message || output.error_code) {
    const explained = output.error_code ? FAILURE_EXPLANATIONS[output.error_code] : undefined;
    return {
      headline: explained ?? output.error_message ?? String(output.error_code),
      details: explained && output.error_message ? [output.error_message] : [],
    };
  }
  const p = output.payload;
  if (!p) return null;
  switch (agentKey) {
    case 'ASSESSMENT':
      return summarizeAssessment(p);
    case 'RESCUE_PLANNING':
      return summarizeRescuePlanning(p);
    case 'HOSPITAL_RECOMMENDATION':
      return summarizeFacilities(p);
    case 'EVACUATION':
      return summarizeRouting(p);
    case 'RESOURCE_COORDINATION':
      return summarizeResources(p);
    case 'SYNTHESIS':
      return summarizeSynthesis(p);
    default:
      return null;
  }
};
