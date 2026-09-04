"""Initial schema for IDRA

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-08-19 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def run_sql(sql: str) -> None:
    for stmt in sql.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            op.execute(stmt)


def upgrade() -> None:
    # Extensions
    run_sql("CREATE EXTENSION IF NOT EXISTS postgis;")
    run_sql("CREATE EXTENSION IF NOT EXISTS vector;")
    run_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # Custom Enum Types
    run_sql("CREATE TYPE user_role AS ENUM ('ADMIN','RESPONDER','CITIZEN');")
    run_sql(
        "CREATE TYPE disaster_type AS ENUM "
        "('FLOOD','EARTHQUAKE','CYCLONE','LANDSLIDE','WILDFIRE','OTHER');"
    )
    run_sql("CREATE TYPE severity_level AS ENUM ('LOW','MODERATE','HIGH','SEVERE');")
    run_sql("CREATE TYPE event_status AS ENUM ('ACTIVE','MONITORING','CLOSED');")
    run_sql("CREATE TYPE facility_type AS ENUM ('HOSPITAL','SHELTER');")
    run_sql("CREATE TYPE report_source AS ENUM ('CITIZEN','RESPONDER','SENSOR','SEED');")
    run_sql("CREATE TYPE run_status AS ENUM ('QUEUED','RUNNING','PARTIAL','COMPLETED','FAILED');")
    run_sql("""
        CREATE TYPE agent_name AS ENUM (
            'DISASTER_ASSESSMENT','RESCUE_PLANNING','EVACUATION',
            'HOSPITAL_RECOMMENDATION','SHELTER_ALLOCATION',
            'RESOURCE_COORDINATION','CITIZEN_ASSISTANCE','SYNTHESIS'
        );
    """)
    run_sql(
        "CREATE TYPE agent_status AS ENUM "
        "('SKIPPED','SUCCESS','FAILED','TIMEOUT','INSUFFICIENT_EVIDENCE');"
    )
    run_sql("CREATE TYPE verification_st AS ENUM ('PENDING','VERIFIED','OVERRIDDEN','REJECTED');")
    run_sql("CREATE TYPE provenance AS ENUM ('REAL','SIMULATED','SYNTHETIC');")
    run_sql("""
        CREATE TYPE resource_kind AS ENUM (
            'MEDICAL_TEAM','RESCUE_BOAT','AMBULANCE','FOOD_KIT',
            'WATER_TANKER','BLANKET_KIT','GENERATOR','RESCUE_TEAM'
        );
    """)

    # 1. users
    run_sql("""
        CREATE TABLE users (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email          TEXT NOT NULL UNIQUE,
            password_hash  TEXT NOT NULL,
            full_name      TEXT NOT NULL,
            role           user_role NOT NULL DEFAULT 'RESPONDER',
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # 2. disaster_events
    run_sql("""
        CREATE TABLE disaster_events (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            TEXT NOT NULL,
            disaster_type   disaster_type NOT NULL,
            status          event_status NOT NULL DEFAULT 'ACTIVE',
            epicenter       GEOMETRY(Point,4326) NOT NULL,
            radius_m        INTEGER NOT NULL CHECK (radius_m BETWEEN 100 AND 50000),
            declared_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at       TIMESTAMPTZ,
            description     TEXT,
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (closed_at IS NULL OR closed_at >= declared_at)
        );
        CREATE INDEX idx_events_epicenter ON disaster_events USING GIST (epicenter);
        CREATE INDEX idx_events_status    ON disaster_events (status, declared_at DESC);
    """)

    # 3. incident_reports
    run_sql("""
        CREATE TABLE incident_reports (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id       UUID REFERENCES disaster_events(id) ON DELETE CASCADE,
            source         report_source NOT NULL,
            reporter_name  TEXT,
            reporter_phone TEXT,
            body           TEXT NOT NULL CHECK (char_length(body) BETWEEN 5 AND 4000),
            location       GEOMETRY(Point,4326) NOT NULL,
            casualties_reported  BOOLEAN NOT NULL DEFAULT FALSE,
            people_affected      INTEGER CHECK (people_affected >= 0),
            data_provenance      provenance NOT NULL DEFAULT 'REAL',
            reported_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_reports_location ON incident_reports USING GIST (location);
        CREATE INDEX idx_reports_event    ON incident_reports (event_id, reported_at DESC);
    """)

    # 4. hazard_zones
    run_sql("""
        CREATE TABLE hazard_zones (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id      UUID REFERENCES disaster_events(id) ON DELETE CASCADE,
            label         TEXT NOT NULL,
            hazard_type   disaster_type NOT NULL,
            severity      severity_level NOT NULL,
            geom          GEOMETRY(Polygon,4326) NOT NULL,
            is_impassable BOOLEAN NOT NULL DEFAULT FALSE,
            active_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
            active_until  TIMESTAMPTZ,
            source_note   TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (active_until IS NULL OR active_until > active_from)
        );
        CREATE INDEX idx_hazard_geom  ON hazard_zones USING GIST (geom);
        CREATE INDEX idx_hazard_event ON hazard_zones (event_id);
        CREATE INDEX idx_hazard_active ON hazard_zones (active_from, active_until);
    """)

    # 5. facilities
    run_sql("""
        CREATE TABLE facilities (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            external_ref      TEXT UNIQUE,
            name              TEXT NOT NULL,
            facility_type     facility_type NOT NULL,
            location          GEOMETRY(Point,4326) NOT NULL,
            address           TEXT,
            total_capacity    INTEGER NOT NULL CHECK (total_capacity >= 0),
            current_occupancy INTEGER NOT NULL DEFAULT 0 CHECK (current_occupancy >= 0),
            specializations   TEXT[] NOT NULL DEFAULT '{}',
            has_generator     BOOLEAN NOT NULL DEFAULT FALSE,
            wheelchair_access BOOLEAN NOT NULL DEFAULT FALSE,
            contact_phone     TEXT,
            is_operational    BOOLEAN NOT NULL DEFAULT TRUE,
            location_provenance provenance NOT NULL DEFAULT 'REAL',
            capacity_provenance provenance NOT NULL DEFAULT 'SIMULATED',
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (current_occupancy <= total_capacity)
        );
        CREATE INDEX idx_fac_location ON facilities USING GIST (location);
        CREATE INDEX idx_fac_type     ON facilities (facility_type, is_operational);
    """)

    # 6. facility_capacity_log
    run_sql("""
        CREATE TABLE facility_capacity_log (
            id            BIGSERIAL PRIMARY KEY,
            facility_id   UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
            occupancy     INTEGER NOT NULL CHECK (occupancy >= 0),
            changed_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            reason        TEXT,
            recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_caplog_fac ON facility_capacity_log (facility_id, recorded_at DESC);
    """)

    # 7. resources
    run_sql("""
        CREATE TABLE resources (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            resource_kind  resource_kind NOT NULL,
            label          TEXT NOT NULL,
            quantity_total INTEGER NOT NULL CHECK (quantity_total >= 0),
            quantity_free  INTEGER NOT NULL CHECK (quantity_free >= 0),
            depot_facility_id UUID REFERENCES facilities(id) ON DELETE SET NULL,
            depot_location GEOMETRY(Point,4326) NOT NULL,
            data_provenance provenance NOT NULL DEFAULT 'SIMULATED',
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (quantity_free <= quantity_total)
        );
        CREATE INDEX idx_res_depot ON resources USING GIST (depot_location);
        CREATE INDEX idx_res_kind  ON resources (resource_kind);
    """)

    # 8. road_nodes
    run_sql("""
        CREATE TABLE road_nodes (
            id        BIGINT PRIMARY KEY,
            geom      GEOMETRY(Point,4326) NOT NULL
        );
        CREATE INDEX idx_rnode_geom ON road_nodes USING GIST (geom);
    """)

    # 9. road_edges
    run_sql("""
        CREATE TABLE road_edges (
            id            BIGSERIAL PRIMARY KEY,
            u             BIGINT NOT NULL REFERENCES road_nodes(id) ON DELETE CASCADE,
            v             BIGINT NOT NULL REFERENCES road_nodes(id) ON DELETE CASCADE,
            key           INTEGER NOT NULL DEFAULT 0,
            osm_way_id    BIGINT,
            highway_class TEXT,
            length_m      DOUBLE PRECISION NOT NULL CHECK (length_m > 0),
            speed_kph     DOUBLE PRECISION NOT NULL CHECK (speed_kph > 0),
            travel_s      DOUBLE PRECISION NOT NULL CHECK (travel_s > 0),
            oneway        BOOLEAN NOT NULL DEFAULT FALSE,
            geom          GEOMETRY(LineString,4326) NOT NULL,
            UNIQUE (u, v, key)
        );
        CREATE INDEX idx_redge_geom ON road_edges USING GIST (geom);
        CREATE INDEX idx_redge_uv   ON road_edges (u, v);
    """)

    # 10. kb_documents
    run_sql("""
        CREATE TABLE kb_documents (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title          TEXT NOT NULL,
            source_type    TEXT NOT NULL,
            source_url     TEXT,
            publisher      TEXT,
            hazard_types   disaster_type[] NOT NULL DEFAULT '{}',
            jurisdiction   TEXT,
            published_at   DATE,
            content_sha256 TEXT NOT NULL UNIQUE,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_kbdoc_hazard ON kb_documents USING GIN (hazard_types);
        CREATE INDEX idx_kbdoc_active ON kb_documents (is_active, published_at DESC);
    """)

    # 11. kb_chunks
    run_sql("""
        CREATE TABLE kb_chunks (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id  UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
            chunk_index  INTEGER NOT NULL,
            section_path TEXT,
            content      TEXT NOT NULL,
            token_count  INTEGER NOT NULL,
            embedding    VECTOR(384) NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, chunk_index)
        );
        CREATE INDEX idx_kbchunk_vec ON kb_chunks
            USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
        CREATE INDEX idx_kbchunk_fts ON kb_chunks
            USING GIN (to_tsvector('english', content));
    """)

    # 12. agent_runs
    run_sql("""
        CREATE TABLE agent_runs (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id           UUID NOT NULL REFERENCES disaster_events(id) ON DELETE CASCADE,
            status             run_status NOT NULL DEFAULT 'QUEUED',
            triggered_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            llm_backend        TEXT,
            llm_model          TEXT,
            assessed_severity  severity_level,
            needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
            total_latency_ms   INTEGER,
            error_code         TEXT,
            started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at        TIMESTAMPTZ
        );
        CREATE INDEX idx_run_event ON agent_runs (event_id, started_at DESC);
    """)

    # 13. agent_outputs
    run_sql("""
        CREATE TABLE agent_outputs (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id        UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            agent         agent_name NOT NULL,
            status        agent_status NOT NULL,
            payload       JSONB,
            prompt_tokens INTEGER,
            output_tokens INTEGER,
            latency_ms    INTEGER,
            retry_count   INTEGER NOT NULL DEFAULT 0,
            error_code    TEXT,
            error_message TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (run_id, agent)
        );
        CREATE INDEX idx_aout_run ON agent_outputs (run_id);
    """)

    # 14. recommendations
    run_sql("""
        CREATE TABLE recommendations (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id         UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            event_id       UUID NOT NULL REFERENCES disaster_events(id) ON DELETE CASCADE,
            agent          agent_name NOT NULL,
            priority       SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 5),
            title          TEXT NOT NULL,
            body           TEXT NOT NULL,
            origin         TEXT NOT NULL DEFAULT 'AI_GENERATED'
                           CHECK (
                             origin IN ('AI_GENERATED','DETERMINISTIC_COMPUTATION','HUMAN_ENTERED')
                           ),
            confidence     NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
            structured_ref JSONB,
            verification_status verification_st NOT NULL DEFAULT 'PENDING',
            verified_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            verified_at    TIMESTAMPTZ,
            override_note  TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (verification_status = 'PENDING' OR verified_by IS NOT NULL)
        );
        CREATE INDEX idx_rec_run   ON recommendations (run_id, priority);
        CREATE INDEX idx_rec_event ON recommendations (event_id, verification_status);
    """)

    # 15. recommendation_citations
    run_sql("""
        CREATE TABLE recommendation_citations (
            id                BIGSERIAL PRIMARY KEY,
            recommendation_id UUID NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
            chunk_id          UUID REFERENCES kb_chunks(id) ON DELETE SET NULL,
            document_title    TEXT NOT NULL,
            source_url        TEXT,
            quoted_span       TEXT,
            relevance_score   NUMERIC(4,3),
            UNIQUE (recommendation_id, chunk_id)
        );
        CREATE INDEX idx_cit_rec ON recommendation_citations (recommendation_id);
    """)

    # 16. routes
    run_sql("""
        CREATE TABLE routes (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id              UUID REFERENCES agent_runs(id) ON DELETE CASCADE,
            event_id            UUID NOT NULL REFERENCES disaster_events(id) ON DELETE CASCADE,
            origin              GEOMETRY(Point,4326) NOT NULL,
            destination         GEOMETRY(Point,4326) NOT NULL,
            destination_facility_id UUID REFERENCES facilities(id) ON DELETE SET NULL,
            path_geom           GEOMETRY(LineString,4326) NOT NULL,
            distance_m          DOUBLE PRECISION NOT NULL,
            duration_s          DOUBLE PRECISION NOT NULL,
            hazard_avoided      BOOLEAN NOT NULL,
            traverses_hazard    BOOLEAN NOT NULL DEFAULT FALSE,
            blocked_edge_count  INTEGER NOT NULL DEFAULT 0,
            algorithm           TEXT NOT NULL DEFAULT 'dijkstra_hazard_penalty',
            supersedes_route_id UUID REFERENCES routes(id) ON DELETE SET NULL,
            computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_route_geom  ON routes USING GIST (path_geom);
        CREATE INDEX idx_route_event ON routes (event_id, computed_at DESC);
    """)

    # 17. resource_allocations
    run_sql("""
        CREATE TABLE resource_allocations (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id            UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            resource_id       UUID NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
            target_zone_label TEXT NOT NULL,
            target_location   GEOMETRY(Point,4326) NOT NULL,
            quantity          INTEGER NOT NULL CHECK (quantity > 0),
            priority          SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 5),
            rationale         TEXT,
            is_committed      BOOLEAN NOT NULL DEFAULT FALSE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_alloc_run ON resource_allocations (run_id);
    """)

    # 18. chat_sessions
    run_sql("""
        CREATE TABLE chat_sessions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id    UUID REFERENCES disaster_events(id) ON DELETE SET NULL,
            client_hash TEXT NOT NULL,
            started_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # 19. chat_messages
    run_sql("""
        CREATE TABLE chat_messages (
            id           BIGSERIAL PRIMARY KEY,
            session_id   UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role         TEXT NOT NULL CHECK (role IN ('USER','ASSISTANT')),
            content      TEXT NOT NULL,
            citations    JSONB,
            escalated    BOOLEAN NOT NULL DEFAULT FALSE,
            latency_ms   INTEGER,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_chatmsg_session ON chat_messages (session_id, created_at);
    """)

    # 20. audit_log
    run_sql("""
        CREATE TABLE audit_log (
            id          BIGSERIAL PRIMARY KEY,
            actor_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            action      TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            before_state JSONB,
            after_state  JSONB,
            request_id  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id, created_at DESC);
    """)


def downgrade() -> None:
    run_sql("DROP TABLE IF EXISTS audit_log CASCADE;")
    run_sql("DROP TABLE IF EXISTS chat_messages CASCADE;")
    run_sql("DROP TABLE IF EXISTS chat_sessions CASCADE;")
    run_sql("DROP TABLE IF EXISTS resource_allocations CASCADE;")
    run_sql("DROP TABLE IF EXISTS routes CASCADE;")
    run_sql("DROP TABLE IF EXISTS recommendation_citations CASCADE;")
    run_sql("DROP TABLE IF EXISTS recommendations CASCADE;")
    run_sql("DROP TABLE IF EXISTS agent_outputs CASCADE;")
    run_sql("DROP TABLE IF EXISTS agent_runs CASCADE;")
    run_sql("DROP TABLE IF EXISTS kb_chunks CASCADE;")
    run_sql("DROP TABLE IF EXISTS kb_documents CASCADE;")
    run_sql("DROP TABLE IF EXISTS road_edges CASCADE;")
    run_sql("DROP TABLE IF EXISTS road_nodes CASCADE;")
    run_sql("DROP TABLE IF EXISTS resources CASCADE;")
    run_sql("DROP TABLE IF EXISTS facility_capacity_log CASCADE;")
    run_sql("DROP TABLE IF EXISTS facilities CASCADE;")
    run_sql("DROP TABLE IF EXISTS hazard_zones CASCADE;")
    run_sql("DROP TABLE IF EXISTS incident_reports CASCADE;")
    run_sql("DROP TABLE IF EXISTS disaster_events CASCADE;")
    run_sql("DROP TABLE IF EXISTS users CASCADE;")

    run_sql("DROP TYPE IF EXISTS resource_kind CASCADE;")
    run_sql("DROP TYPE IF EXISTS provenance CASCADE;")
    run_sql("DROP TYPE IF EXISTS verification_st CASCADE;")
    run_sql("DROP TYPE IF EXISTS agent_status CASCADE;")
    run_sql("DROP TYPE IF EXISTS agent_name CASCADE;")
    run_sql("DROP TYPE IF EXISTS run_status CASCADE;")
    run_sql("DROP TYPE IF EXISTS report_source CASCADE;")
    run_sql("DROP TYPE IF EXISTS facility_type CASCADE;")
    run_sql("DROP TYPE IF EXISTS event_status CASCADE;")
    run_sql("DROP TYPE IF EXISTS severity_level CASCADE;")
    run_sql("DROP TYPE IF EXISTS disaster_type CASCADE;")
    op.execute("DROP TYPE IF EXISTS user_role CASCADE;")
