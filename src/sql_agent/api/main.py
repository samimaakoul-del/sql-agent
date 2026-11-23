"""Point d'entrée de l'API.

Lancer en local :  uvicorn sql_agent.api.main:app --reload
Documentation auto : http://localhost:8000/docs
"""

from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from sql_agent import __version__
from sql_agent.analyzer import AnalysisError, analyze
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


class AnalyzeIn(BaseModel):
    sql: str


class FindingOut(BaseModel):
    rule: str
    table: str | None
    message: str
    candidate: str | None
    candidate_ddl: str | None


class DiagnosisOut(BaseModel):
    query: str
    analyzed_query: str
    total_cost: float
    primary_cause: str | None
    findings: list[FindingOut]
    candidates: list[str]
    candidates_ddl: list[str]
    rewrite_hint: str | None
    plan: dict[str, Any]


@app.post("/analyze", response_model=DiagnosisOut)
def analyze_query(body: AnalyzeIn, conn: Connection) -> DiagnosisOut:
    """F2 – Lit le plan EXPLAIN (sans exécuter la requête) et diagnostique le problème.

    Accepte une requête avec ses valeurs, ou normalisée ($1, $2…) depuis /slow-queries.
    Les index renvoyés sont des **propositions** : rien n'est créé.
    """
    try:
        d = analyze(conn, body.sql)
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DiagnosisOut(
        query=d.query,
        analyzed_query=d.analyzed_query,
        total_cost=d.total_cost,
        primary_cause=d.primary_cause,
        findings=[
            FindingOut(
                rule=f.rule,
                table=f.table,
                message=f.message,
                candidate=str(f.candidate) if f.candidate else None,
                candidate_ddl=f.candidate.ddl() if f.candidate else None,
            )
            for f in d.findings
        ],
        candidates=[str(c) for c in d.candidates],
        candidates_ddl=[c.ddl() for c in d.candidates],
        rewrite_hint=d.rewrite_hint,
        plan=d.plan,
    )
