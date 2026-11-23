"""F2 - Obtenir le plan d'exécution d'une requête, sans jamais l'exécuter.

On utilise EXPLAIN (GENERIC_PLAN) – PostgreSQL 16 – qui accepte les requêtes
normalisées de pg_stat_statements (« WHERE id = $1 ») et n'exécute rien.
"""

import re
from typing import Any

import psycopg
from psycopg import sql

from sql_agent.analyzer import rules
from sql_agent.analyzer.models import Diagnosis, TableInfo

Connection = psycopg.Connection[tuple[Any, ...]]


class AnalysisError(Exception):
    """Requête impossible à analyser ; le message est destiné à l'utilisateur."""


# pg_stat_statements transforme « interval '7 days' » en « interval $2 », qui n'est
# plus du SQL valide. On le réécrit en « $2::interval », équivalent et valide.
_TYPED_PARAM = re.compile(r"\b(interval|date|timestamptz|timestamp|time)\s+(\$\d+)", re.I)


def check_is_single_select(query: str) -> str:
    """Contrôle minimal : une seule requête de lecture (SELECT ou WITH).

    Les garde-fous complets (F6) sont dans le module guardrails ; ici on s'assure
    simplement de ne passer à EXPLAIN qu'une requête de lecture.
    """
    q = query.strip().rstrip(";").strip()
    if not q:
        raise AnalysisError("Requête vide.")
    if ";" in q:
        raise AnalysisError("Une seule requête à la fois (point-virgule interdit au milieu).")
    if not re.match(r"(?is)^(select|with)\b", q):
        raise AnalysisError("Seules les requêtes de lecture (SELECT / WITH) sont analysées.")
    return q


def explain(conn: Connection, query: str) -> tuple[dict[str, Any], str]:
    """Renvoie (plan JSON, requête réellement analysée). N'exécute pas la requête."""
    q = check_is_single_select(query)
    attempts = [q]
    fixed = _TYPED_PARAM.sub(r"\2::\1", q)
    if fixed != q:
        attempts.insert(0, fixed)

    last_error: psycopg.Error | None = None
    for attempt in attempts:
        stmt = sql.SQL("EXPLAIN (GENERIC_PLAN, FORMAT JSON) ") + sql.SQL(attempt)
        try:
            row = conn.execute(stmt).fetchone()
        except psycopg.Error as exc:
            last_error = exc
            continue
        assert row is not None
        return row[0][0]["Plan"], attempt

    detail = (last_error.diag.message_primary if last_error else None) or str(last_error)
    hint = (
        " Cette requête vient de pg_stat_statements (valeurs remplacées par $1, $2…) : "
        "collez-la avec de vraies valeurs pour l'analyser."
        if "$" in q
        else ""
    )
    raise AnalysisError(f"PostgreSQL ne peut pas planifier cette requête : {detail}.{hint}")


_TABLE_INFO = """
SELECT c.relname,
       greatest(c.reltuples, 0) AS rows,
       array(SELECT a.attname FROM pg_attribute a
             WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) AS columns,
       array(SELECT a.attname FROM pg_index i
             JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
             WHERE i.indrelid = c.oid) AS indexed
FROM pg_class c
WHERE c.oid = ANY(%s::regclass[])
"""


def table_info(conn: Connection, tables: set[str]) -> dict[str, TableInfo]:
    """Taille, colonnes et colonnes déjà indexées des tables du plan."""
    if not tables:
        return {}
    rows = conn.execute(_TABLE_INFO, (sorted(tables),)).fetchall()
    return {
        name: TableInfo(float(n), frozenset(cols), frozenset(idx)) for name, n, cols, idx in rows
    }


def analyze(conn: Connection, query: str) -> Diagnosis:
    """Analyse complète : plan + métadonnées + règles."""
    plan, analyzed = explain(conn, query)
    tables = table_info(conn, set(rules.relations(plan).values()))
    findings = rules.diagnose(plan, tables)
    cause = rules.primary_cause(findings)
    hint = (
        "Remplacer « colonne::date = jour » par « colonne >= jour AND colonne < jour + 1 »."
        if cause == "cast_empeche_index"
        else None
    )
    return Diagnosis(
        query=query,
        analyzed_query=analyzed,
        total_cost=float(plan["Total Cost"]),
        primary_cause=cause,
        findings=findings,
        candidates=rules.candidates(findings),
        rewrite_hint=hint,
        plan=plan,
    )
