export type UserRole = 'ADMIN' | 'RESPONDER' | 'CITIZEN';

export type DisasterType =
  | 'FLOOD'
  | 'EARTHQUAKE'
  | 'CYCLONE'
  | 'LANDSLIDE'
  | 'WILDFIRE'
  | 'OTHER';

export type SeverityLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE';

export type EventStatus = 'ACTIVE' | 'MONITORING' | 'CLOSED';

export type FacilityType = 'HOSPITAL' | 'SHELTER';

export type ReportSource = 'CITIZEN' | 'RESPONDER' | 'SENSOR' | 'SEED';

export type Provenance = 'REAL' | 'SIMULATED' | 'SYNTHETIC';

export interface EpicenterPoint {
  lon: number;
  lat: number;
}

export interface Facility {
  id: string;
  name: string;
  facility_type: FacilityType;
  location: EpicenterPoint;
  total_capacity: number;
  current_occupancy: number;
  is_operational: boolean;
  phone?: string | null;
  address?: string | null;
}

export interface FacilityListResponse {
  items: Facility[];
  total: number;
}

export interface DisasterEvent {
  id: string;
  name: string;
  disaster_type: DisasterType;
  status: EventStatus;
  epicenter: EpicenterPoint;
  radius_m: number;
  declared_at: string;
  closed_at?: string | null;
  description?: string | null;
  created_by?: string | null;
  created_at: string;
  report_count: number;
  hazard_zone_count: number;
}

export interface EventListResponse {
  items: DisasterEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventCreateInput {
  name: string;
  disaster_type: DisasterType;
  epicenter: EpicenterPoint;
  radius_m: number;
  description?: string;
}

export interface IncidentReport {
  id: string;
  event_id?: string | null;
  source: ReportSource;
  reporter_name?: string | null;
  reporter_phone?: string | null;
  body: string;
  location: EpicenterPoint;
  casualties_reported: boolean;
  people_affected?: number | null;
  data_provenance: Provenance;
  reported_at: string;
  created_at: string;
}

export interface ReportListResponse {
  items: IncidentReport[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReportCreateInput {
  event_id?: string;
  source?: ReportSource;
  reporter_name?: string;
  reporter_phone?: string;
  body: string;
  location: EpicenterPoint;
  casualties_reported?: boolean;
  people_affected?: number;
}

export interface GeoJSONPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface HazardZone {
  id: string;
  event_id: string;
  label: string;
  hazard_type: DisasterType;
  severity: SeverityLevel;
  geometry: GeoJSONPolygon;
  is_impassable: boolean;
  active_from: string;
  active_until?: string | null;
  source_note?: string | null;
  created_at: string;
}

export interface HazardZoneListResponse {
  items: HazardZone[];
  total: number;
}

export interface HazardZoneCreateInput {
  event_id: string;
  label: string;
  hazard_type: DisasterType;
  severity: SeverityLevel;
  geometry: GeoJSONPolygon;
  is_impassable?: boolean;
  active_from?: string;
  active_until?: string;
  source_note?: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
    timestamp: string;
  };
}

export type VerificationStatus = 'PENDING' | 'VERIFIED' | 'OVERRIDDEN' | 'REJECTED';

export type Origin = 'AI_GENERATED' | 'DETERMINISTIC_COMPUTATION' | 'HUMAN_ENTERED';

export interface RecommendationCitation {
  id: number;
  document_title: string;
  source_type: string;
  source_url?: string | null;
  section_path?: string | null;
  quoted_span?: string | null;
  relevance_score?: number | null;
}

export interface Recommendation {
  id: string;
  run_id: string;
  event_id: string;
  agent: string;
  priority: number;
  title: string;
  body: string;
  origin: Origin;
  confidence?: number | null;
  structured_ref?: Record<string, unknown> | null;
  verification_status: VerificationStatus;
  verified_by?: string | null;
  verified_at?: string | null;
  override_note?: string | null;
  created_at: string;
  citations: RecommendationCitation[];
}

export interface RecommendationListResponse {
  items: Recommendation[];
  total: number;
}

export interface VerifyRecommendationInput {
  action: VerificationStatus;
  note?: string;
}

export interface AgentOutput {
  id: string;
  agent: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  payload?: Record<string, unknown> | null;
  latency_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
}

// Hazard-avoiding route computed by the Evacuation Routing agent (RoutingOutput.routes).
export interface EvacuationRoute {
  route_id: string;
  origin: EpicenterPoint;
  destination: EpicenterPoint;
  destination_facility_id?: string | null;
  destination_name: string;
  geometry: { type: 'LineString'; coordinates: [number, number][] };
  distance_m: number;
  duration_s: number;
  hazard_avoided: boolean;
  traverses_hazard: boolean;
  blocked_edges_avoided: number;
  rationale: string;
}

export interface RunDetail {
  id: string;
  event_id: string;
  status: string;
  triggered_by?: string | null;
  assessed_severity?: SeverityLevel | null;
  needs_human_review: boolean;
  total_latency_ms?: number | null;
  started_at: string;
  finished_at?: string | null;
  outputs: AgentOutput[];
}

export interface CitizenQueryInput {
  query: string;
  location?: EpicenterPoint;
  session_id?: string;
  event_id?: string;
}

export interface CitizenCitation {
  chunk_id?: string;
  document_title: string;
  quoted_span?: string | null;
  relevance_score?: number | null;
}

export interface NearestFacilityItem {
  facility_id: string;
  name: string;
  facility_type: FacilityType;
  distance_m: number;
  capacity_provenance: string;
}

export interface CitizenQueryResponse {
  session_id: string;
  answer: string;
  citations: CitizenCitation[];
  nearest_facilities: NearestFacilityItem[];
  escalated: boolean;
  escalation_reason?: string | null;
  safety_flag: 'NONE' | 'URGENT' | 'LIFE_THREATENING';
  disclaimer: string;
}

