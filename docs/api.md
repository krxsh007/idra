# IDRA REST & SSE API Reference (`/api/v1`)

## 1. Authentication & RBAC
IDRA uses JWT Bearer authentication (`POST /api/v1/auth/login`) with three hierarchical roles:
- `CITIZEN`: Can submit emergency field reports and query the Citizen Assistant.
- `RESPONDER`: Inherits `CITIZEN`; can view events, facilities, hazard zones, trigger orchestration runs, export SitReps, and inspect evaluation metrics.
- `ADMIN`: Inherits `RESPONDER`; can create/close events, manage hazard polygons, seed scenarios, and verify/override/reject recommendations (`POST /api/v1/recommendations/{rec_id}/verify`).

### Seeded Accounts
| Email | Password | Role |
|---|---|---|
| `admin@example.com` | value of `SEED_ADMIN_PASSWORD` in `.env` (`change_me_secure_password_123` in `.env.example`) | `ADMIN` |
| `responder1@example.com` | `responder_password_1` | `RESPONDER` |
| `responder2@example.com` | `responder_password_2` | `RESPONDER` |

There is no seeded `CITIZEN` login: the Citizen Assistant (`POST /api/v1/assistant/query`) and incident reporting (`POST /api/v1/reports`) are public and rate-limited. Note that `.local` addresses are rejected by the login email validator.

---

## 2. Endpoint Summary

### Health & Diagnostics
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/health` and `/api/v1/health/deep` | Public | Liveness, plus per-component health (database, road graph, LLM backend) on `/health/deep` |
| `GET` | `/api/v1/metrics/eval` | `RESPONDER+` | Returns evaluation suite results (`rag_eval`, `agent_eval`, `gis_eval`, `system_eval`, `ui_study`) |

### Authentication (`/api/v1/auth`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Public | Exchange `email` and `password` for JWT `access_token` |
| `GET` | `/api/v1/auth/me` | `CITIZEN+` | Retrieve authenticated user profile and role |

### Events & Scenarios (`/api/v1/events`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/events` | `RESPONDER+` | List active and historical disaster events |
| `POST` | `/api/v1/events` | `ADMIN` | Create a new disaster event within `STUDY_AREA_BBOX` |
| `GET` | `/api/v1/events/{event_id}` | `RESPONDER+` | Retrieve event metadata, epicenter, and weather snapshot |
| `PATCH` | `/api/v1/events/{event_id}` | `ADMIN` | Update event status or metadata |
| `GET` | `/api/v1/events/{event_id}/geojson` | `RESPONDER+` | Event, hazard zones and routes as GeoJSON |

### Field Reports (`/api/v1/events/{event_id}/reports`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/events/{event_id}/reports` | `RESPONDER+` | List geocoded citizen/responder field reports for an event |
| `POST` | `/api/v1/reports` | Public (Rate-Limited) | Submit a new geocoded field report (see `ReportCreate` schema) |

### Hazard Zones
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/events/{event_id}/hazard-zones` | `RESPONDER+` | List active hazard polygons (`GeoJSON`) for an event |
| `POST` | `/api/v1/hazard-zones` | `ADMIN` | Create a validated `Polygon` hazard zone (`ST_IsValid` enforced) |
| `PATCH` | `/api/v1/hazard-zones/{zone_id}` | `ADMIN` | Update severity or deactivate a hazard polygon |

### Facilities (`/api/v1/facilities`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/facilities` | Public | Query hospitals/shelters with optional spatial radius (`lon`, `lat`, `radius_m`) and `facility_type` |

### Orchestration Runs, Recommendations & SitRep
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/events/{event_id}/runs` | `RESPONDER+` | Trigger the 7-agent orchestration pipeline for `event_id` |
| `GET` | `/api/v1/runs/{run_id}` | `RESPONDER+` | Fetch run status, `AgentOutput` traces, recommendations, and resource allocations |
| `GET` | `/api/v1/runs/{run_id}/stream` | `RESPONDER+` | Subscribe to Server-Sent Events (`SSE`) for real-time agent stage transitions |
| `GET` | `/api/v1/events/{event_id}/runs` | `RESPONDER+` | List runs for an event |
| `GET` | `/api/v1/events/{event_id}/recommendations` | `RESPONDER+` | List recommendations for an event |
| `GET` | `/api/v1/events/{event_id}/routes` | `RESPONDER+` | List computed evacuation routes |
| `GET` | `/api/v1/recommendations` | `RESPONDER+` | List recommendations (filter by `verification_status`) |
| `POST` | `/api/v1/recommendations/{rec_id}/verify` | `ADMIN` | Verify, override, or reject a `PENDING` recommendation and optionally commit allocations |

### Citizen Assistant (`/api/v1/assistant/query`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/assistant/query` | Public (Rate-Limited) | Multilingual (`en`/`ta`/`hi`) RAG-grounded citizen Q&A with nearest-shelter lookup and urgent distress escalation |
