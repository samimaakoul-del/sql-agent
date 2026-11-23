"""F1 - Repérer les requêtes les plus coûteuses à partir de pg_stat_statements."""

from dataclasses import dataclass
from typing import Literal

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

OrderBy = Literal["total", "mean"]

# Liste blanche : le critère de tri n'est JAMAIS inséré tel quel dans le SQL.
_ORDER_COLUMNS: dict[str, str] = {
    "total": "total_exec_time",  # coût cumulé : ce qui pèse le plus sur le serveur
    "mean": "mean_exec_time",  # coût unitaire : ce que ressent l'utilisateur à chaque appel
}

_QUERY = """
SELECT queryid,
       query,
       calls,
       total_exec_time                                          AS total_ms,
       mean_exec_time                                           AS mean_ms,
       rows,
       100 * total_exec_time / NULLIF(sum(total_exec_time) OVER (), 0) AS share_pct
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  -- on ignore les requêtes de l'agent lui-même
  AND userid <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
  AND calls >= %(min_calls)s
ORDER BY {order_column} DESC
LIMIT %(limit)s
"""


@dataclass(frozen=True)
class SlowQuery:
    """Une forme de requête (les constantes sont remplacées par $1, $2...)."""

    queryid: int
    query: str
    calls: int
    total_ms: float
    mean_ms: float
    rows: int
    share_pct: float


def fetch_slow_queries(
    conn: psycopg.Connection[tuple[object, ...]],
    limit: int = 10,
    order_by: OrderBy = "total",
    min_calls: int = 1,
) -> list[SlowQuery]:
    """Renvoie les requêtes les plus coûteuses, de la plus coûteuse à la moins coûteuse."""
    if order_by not in _ORDER_COLUMNS:
        raise ValueError(f"order_by doit valoir {sorted(_ORDER_COLUMNS)}, reçu {order_by!r}")
    if not 1 <= limit <= 100:
        raise ValueError("limit doit être entre 1 et 100")

    query = sql.SQL(_QUERY).format(order_column=sql.Identifier(_ORDER_COLUMNS[order_by]))
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(query, {"limit": limit, "min_calls": min_calls}).fetchall()
    return [
        SlowQuery(
            queryid=int(r["queryid"]),
            query=" ".join(str(r["query"]).split()),  # espaces multiples -> un seul
            calls=int(r["calls"]),
            total_ms=round(float(r["total_ms"]), 2),
            mean_ms=round(float(r["mean_ms"]), 2),
            rows=int(r["rows"]),
            share_pct=round(float(r["share_pct"] or 0), 1),
        )
        for r in rows
    ]
