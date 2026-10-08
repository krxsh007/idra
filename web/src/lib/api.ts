import {
  ApiError,
  CitizenQueryInput,
  CitizenQueryResponse,
  DisasterEvent,
  EventCreateInput,
  EventListResponse,
  FacilityListResponse,
  HazardZone,
  HazardZoneCreateInput,
  HazardZoneListResponse,
  IncidentReport,
  Recommendation,
  RecommendationListResponse,
  ReportCreateInput,
  ReportListResponse,
  RunDetail,
  TokenResponse,
  User,
  VerificationStatus,
  VerifyRecommendationInput,
} from '../types/api';

const API_BASE = '/api/v1';

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem('idra_access_token');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorData: ApiError;
      try {
        errorData = await response.json();
      } catch {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      throw new Error(errorData.error?.message || `Request failed with status ${response.status}`);
    }

    return response.json();
  }

  // Auth
  async login(email: string, password: string): Promise<TokenResponse> {
    return this.request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  // Events
  async getEvents(status?: string): Promise<EventListResponse> {
    const query = status ? `?status=${status}` : '';
    return this.request<EventListResponse>(`/events${query}`);
  }

  async getEvent(id: string): Promise<DisasterEvent> {
    return this.request<DisasterEvent>(`/events/${id}`);
  }

  async createEvent(data: EventCreateInput): Promise<DisasterEvent> {
    return this.request<DisasterEvent>('/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Reports
  async submitReport(data: ReportCreateInput): Promise<IncidentReport> {
    return this.request<IncidentReport>('/reports', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getEventReports(eventId: string): Promise<ReportListResponse> {
    return this.request<ReportListResponse>(`/events/${eventId}/reports`);
  }

  // Hazard Zones
  async getEventHazardZones(eventId: string): Promise<HazardZoneListResponse> {
    return this.request<HazardZoneListResponse>(`/events/${eventId}/hazard-zones`);
  }

  async createHazardZone(data: HazardZoneCreateInput): Promise<HazardZone> {
    return this.request<HazardZone>('/hazard-zones', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Recommendations & Verification
  async getRecommendations(
    eventId?: string,
    status?: VerificationStatus
  ): Promise<RecommendationListResponse> {
    const params = new URLSearchParams();
    if (eventId) params.append('event_id', eventId);
    if (status) params.append('verification_status', status);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.request<RecommendationListResponse>(`/recommendations${qs}`);
  }

  async verifyRecommendation(
    recId: string,
    data: VerifyRecommendationInput
  ): Promise<Recommendation> {
    return this.request<Recommendation>(`/recommendations/${recId}/verify`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Runs
  async triggerRun(eventId: string, force = false): Promise<RunDetail> {
    return this.request<RunDetail>('/runs', {
      method: 'POST',
      body: JSON.stringify({ event_id: eventId, force }),
    });
  }

  async getEventRuns(eventId: string): Promise<{ items: RunDetail[]; total: number }> {
    return this.request<{ items: RunDetail[]; total: number }>(`/events/${eventId}/runs`);
  }

  // Citizen Assistant
  async queryAssistant(data: CitizenQueryInput): Promise<CitizenQueryResponse> {
    return this.request<CitizenQueryResponse>('/assistant/query', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // GeoJSON Multi-layer
  async getEventGeoJson(eventId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/events/${eventId}/geojson`);
  }

  // Facilities
  async getFacilities(): Promise<FacilityListResponse> {
    return this.request<FacilityListResponse>('/facilities?limit=100');
  }
}

export const api = new ApiClient();
