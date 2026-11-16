# PostgreSQL 16 + HypoPG (index hypothétiques : tester un index sans le créer)
# pg_stat_statements est déjà inclus dans l'image officielle (contrib).
FROM postgres:16

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-hypopg \
    && rm -rf /var/lib/apt/lists/*

# Scripts exécutés au premier démarrage (base vide uniquement)
COPY init/ /docker-entrypoint-initdb.d/
