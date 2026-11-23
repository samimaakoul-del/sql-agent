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
from sql_agent.analyzer.explain import table_info
from sql_agent.analyzer.rules import relations
from sql_agent.collector import fetch_slow_queries
from sql_agent.collector.slow_queries import OrderBy
from sql_agent.db import connect
from sql_agent.validator import InvalidIndexError, ValidationResult, evaluate, parse_index_ddl

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
    rewritten_query: str | None
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
        rewritten_query=d.rewritten_query,
        plan=d.plan,
    )


class ValidateIn(BaseModel):
    sql: str
    # Index à tester (ex. proposés par le LLM). Absent : ceux trouvés par l'analyseur.
    indexes: list[str] | None = None


class IndexEvaluationOut(BaseModel):
    index: str
    ddl: str
    cost_after: float
    gain_pct: float
    used: bool
    size_mb: float


class ValidationOut(BaseModel):
    query: str
    cost_before: float
    combined_cost_after: float | None
    combined_gain_pct: float | None
    min_gain_pct: float
    evaluations: list[IndexEvaluationOut]
    accepted: list[str]
    accepted_size_mb: float


class RejectedIndexOut(BaseModel):
    ddl: str
    reason: str


class ValidateOut(BaseModel):
    primary_cause: str | None
    original: ValidationOut
    rewritten: ValidationOut | None
    rejected_indexes: list[RejectedIndexOut]
    recommendation: str


def _mb(size_bytes: int) -> float:
    return round(size_bytes / 1_000_000, 1)


def _validation_out(r: ValidationResult) -> ValidationOut:
    return ValidationOut(
        query=r.query,
        cost_before=r.cost_before,
        combined_cost_after=r.combined_cost_after,
        combined_gain_pct=r.combined_gain_pct,
        min_gain_pct=r.min_gain_pct,
        evaluations=[
            IndexEvaluationOut(
                index=str(e.candidate),
                ddl=e.candidate.ddl(),
                cost_after=e.cost_after,
                gain_pct=e.gain_pct,
                used=e.used,
                size_mb=_mb(e.size_bytes),
            )
            for e in r.evaluations
        ],
        accepted=[c.ddl() for c in r.accepted],
        accepted_size_mb=_mb(r.accepted_size_bytes),
    )


def _recommendation(original: ValidationResult, rewritten: ValidationResult | None) -> str:
    best = original
    if rewritten and (rewritten.combined_gain_pct or 0) > (original.combined_gain_pct or 0):
        best = rewritten
    if not best.accepted:
        if not best.evaluations:
            return "Aucun index classique ne peut aider cette requête."
        return (
            f"Aucun index testé n'apporte au moins {best.min_gain_pct:.0f} % de gain : "
            "ne rien créer."
        )
    prefix = "Réécrire la requête, puis créer : " if best is rewritten else "Créer : "
    return (
        f"{prefix}{' ; '.join(c.ddl() for c in best.accepted)} "
        f"(gain estimé {best.combined_gain_pct:.1f} %, ~{_mb(best.accepted_size_bytes)} Mo). "
        "À faire valider par un humain avant toute création."
    )


@app.post("/validate", response_model=ValidateOut)
def validate_indexes(body: ValidateIn, conn: Connection) -> ValidateOut:
    """F5 – Teste les index proposés avec HypoPG (index hypothétiques) : **rien n'est créé**.

    Compare le coût estimé avant / après ; un index n'est retenu que si le gain
    atteint 30 %. Si la requête peut être réécrite, la version réécrite est testée aussi.
    """
    try:
        d = analyze(conn, body.sql)
        rejected: list[RejectedIndexOut] = []
        if body.indexes is None:
            candidates = d.candidates
        else:
            tables = table_info(conn, set(relations(d.plan).values()))
            candidates = []
            for ddl in body.indexes:
                try:
                    candidates.append(parse_index_ddl(ddl, tables))
                except InvalidIndexError as exc:
                    rejected.append(RejectedIndexOut(ddl=ddl, reason=str(exc)))
        original = evaluate(conn, d.analyzed_query, candidates)
        rewritten = evaluate(conn, d.rewritten_query, candidates) if d.rewritten_query else None
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ValidateOut(
        primary_cause=d.primary_cause,
        original=_validation_out(original),
        rewritten=_validation_out(rewritten) if rewritten else None,
        rejected_indexes=rejected,
        recommendation=_recommendation(original, rewritten),
    )
