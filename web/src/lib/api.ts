import {
  ApiError,
  DisasterEvent,
  EventCreateInput,
  EventListResponse,
  HazardZone,
  HazardZoneCreateInput,
  HazardZoneListResponse,
  IncidentReport,
  ReportCreateInput,
  ReportListResponse,
  TokenResponse,
  User,
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
}

export const api = new ApiClient();
