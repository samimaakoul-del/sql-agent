"""F1 - Collecteur : top des requêtes coûteuses depuis pg_stat_statements.

Responsable : Ahmed Sami.
"""

from sql_agent.collector.slow_queries import SlowQuery, fetch_slow_queries

__all__ = ["SlowQuery", "fetch_slow_queries"]
