"""Connexion à la base, toujours en lecture seule.

Double protection (garde-fou F6) :
  1. le rôle agent_ro n'a que des droits de lecture (côté PostgreSQL) ;
  2. chaque connexion force default_transaction_read_only=on (côté agent).
"""

import psycopg

from sql_agent.config import settings


def connect(url: str | None = None) -> psycopg.Connection[tuple[object, ...]]:
    """Ouvre une connexion en lecture seule (timeout court pour échouer vite)."""
    return psycopg.connect(
        url or settings.database_url,
        autocommit=True,
        connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
    )
