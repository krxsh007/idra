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

export type ReportSource = 'CITIZEN' | 'RESPONDER' | 'SENSOR' | 'SEED';

export type Provenance = 'REAL' | 'SIMULATED' | 'SYNTHETIC';

export interface EpicenterPoint {
  lon: number;
  lat: number;
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
