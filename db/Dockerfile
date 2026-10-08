FROM postgis/postgis:16-3.4

# bullseye-pgdg has moved to the PostgreSQL apt archive
RUN sed -i 's|apt.postgresql.org/pub/repos/apt|apt-archive.postgresql.org/pub/repos/apt|' /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
