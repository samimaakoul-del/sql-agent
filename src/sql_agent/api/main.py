"""Point d'entrée de l'API.

Lancer en local :  uvicorn sql_agent.api.main:app --reload
Documentation auto : http://localhost:8000/docs
"""

from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from sql_agent import __version__
from sql_agent.collector import fetch_slow_queries
from sql_agent.collector.slow_queries import OrderBy
from sql_agent.db import connect

app = FastAPI(
    title="SQL Agent",
    description="Repère, explique et corrige les requêtes SQL lentes – sans modifier la base.",
    version=__version__,
)


def get_connection() -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """Une connexion lecture seule par requête HTTP. Base injoignable -> 503 clair."""
    try:
        conn = connect()
    except psycopg.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="Base de données injoignable. Vérifiez que le service « db » est démarré.",
        ) from exc
    try:
        yield conn
    finally:
        conn.close()


Connection = Annotated[psycopg.Connection[tuple[object, ...]], Depends(get_connection)]


class SlowQueryOut(BaseModel):
    queryid: int
    query: str
    calls: int
    total_ms: float
    mean_ms: float
    rows: int
    share_pct: float


@app.get("/health")
def health() -> dict[str, str]:
    """Vérifie que l'API répond (utilisé par Docker et la CI)."""
    return {"status": "ok", "version": __version__}


@app.get("/slow-queries", response_model=list[SlowQueryOut])
def slow_queries(
    conn: Connection,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    order_by: OrderBy = "total",
    min_calls: Annotated[int, Query(ge=1)] = 1,
) -> list[SlowQueryOut]:
    """F1 – Top des requêtes les plus coûteuses (pg_stat_statements).

    - `order_by=total` : coût cumulé (charge sur le serveur)
    - `order_by=mean` : coût par appel (ressenti utilisateur)
    """
    try:
        found = fetch_slow_queries(conn, limit=limit, order_by=order_by, min_calls=min_calls)
    except psycopg.errors.UndefinedTable as exc:
        raise HTTPException(
            status_code=503,
            detail="Extension pg_stat_statements absente de la base.",
        ) from exc
    return [SlowQueryOut(**asdict(q)) for q in found]
