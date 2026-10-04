# IDRA REST & SSE API Reference (`/api/v1`)

## 1. Authentication & RBAC
IDRA uses JWT Bearer authentication (`POST /api/v1/auth/login`) with three hierarchical roles:
- `CITIZEN`: Can submit emergency field reports and query the Citizen Assistant.
- `RESPONDER`: Inherits `CITIZEN`; can view events, facilities, hazard zones, trigger orchestration runs, export SitReps, and inspect evaluation metrics.
- `ADMIN`: Inherits `RESPONDER`; can create/close events, manage hazard polygons, seed scenarios, and verify/override/reject recommendations (`POST /api/v1/recommendations/{id}/verify`).

### Seeded Accounts
| Email | Password | Role |
|---|---|---|
| `admin@idra.local` | `AdminPass123!` | `ADMIN` |
| `responder@idra.local` | `ResponderPass123!` | `RESPONDER` |
| `citizen@idra.local` | `CitizenPass123!` | `CITIZEN` |

---

## 2. Endpoint Summary

### Health & Diagnostics
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | Public | Returns service health across PostgreSQL/PostGIS, Redis, Road Graph (`1,748` nodes), and LLM backend |
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
| `POST` | `/api/v1/events/scenarios/{key}/activate` | `ADMIN` | Seed and activate a canonical scenario (`chennai_flood`, `coastal_cyclone`, `building_collapse`) |

### Field Reports (`/api/v1/events/{event_id}/reports`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/events/{event_id}/reports` | `RESPONDER+` | List geocoded citizen/responder field reports for an event |
| `POST` | `/api/v1/events/{event_id}/reports` | `CITIZEN+` | Submit a new geocoded field report (`people_affected`, `casualties_reported`, `body`) |

### Hazard Zones (`/api/v1/events/{event_id}/hazards`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/events/{event_id}/hazards` | `RESPONDER+` | List active hazard polygons (`GeoJSON`) for an event |
| `POST` | `/api/v1/events/{event_id}/hazards` | `ADMIN` | Create a validated `Polygon` hazard zone (`ST_IsValid` enforced) |
| `DELETE` | `/api/v1/events/{event_id}/hazards/{hazard_id}` | `ADMIN` | Deactivate a hazard polygon |

### Facilities & Resources (`/api/v1/facilities`, `/api/v1/resources`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/facilities` | `RESPONDER+` | Query hospitals/shelters with optional spatial radius (`lon`, `lat`, `radius_m`) and `facility_type` |
| `GET` | `/api/v1/resources` | `RESPONDER+` | List emergency response units (`MEDICAL_TEAM`, `RESCUE_BOAT`, `AMBULANCE`, etc.) |

### Orchestration Runs, Recommendations & SitRep
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/events/{event_id}/runs` | `RESPONDER+` | Trigger the 7-agent orchestration pipeline for `event_id` |
| `GET` | `/api/v1/runs/{run_id}` | `RESPONDER+` | Fetch run status, `AgentOutput` traces, recommendations, and resource allocations |
| `GET` | `/api/v1/runs/{run_id}/stream` | `RESPONDER+` | Subscribe to Server-Sent Events (`SSE`) for real-time agent stage transitions |
| `GET` | `/api/v1/runs/{run_id}/sitrep` | `RESPONDER+` | Export printable Markdown Situation Report (`SitRep`) |
| `POST` | `/api/v1/recommendations/{id}/verify` | `ADMIN` | Verify, override, or reject a `PENDING` recommendation and optionally commit allocations |

### Citizen Assistant (`/api/v1/assistant/query`)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/assistant/query` | Public (Rate-Limited) | Multilingual (`en`/`ta`/`hi`) RAG-grounded citizen Q&A with nearest-shelter lookup and urgent distress escalation |
