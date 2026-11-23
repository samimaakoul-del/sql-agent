"""F5 - Tester un index SANS le créer, grâce aux index hypothétiques (HypoPG).

Principe : on crée l'index « pour de faux » (il n'existe que dans la mémoire de
notre session), on redemande le plan à PostgreSQL et on compare le coût estimé.
Rien n'est écrit sur le disque ; tout fonctionne avec le rôle en lecture seule.
"""

from dataclasses import dataclass, field
from typing import Any

import psycopg

from sql_agent.analyzer.explain import explain
from sql_agent.analyzer.models import IndexCandidate
from sql_agent.analyzer.rules import walk

Connection = psycopg.Connection[tuple[Any, ...]]

MIN_GAIN_PCT = 30.0  # seuil de la fiche de cadrage (F5)


@dataclass(frozen=True)
class IndexEvaluation:
    """Effet d'un index testé seul."""

    candidate: IndexCandidate
    cost_after: float
    gain_pct: float
    used: bool  # PostgreSQL l'utilise-t-il vraiment dans le nouveau plan ?
    size_bytes: int  # taille estimée de l'index (coût en stockage et en écriture)


@dataclass
class ValidationResult:
    """Résultat de la validation d'un ensemble d'index pour une requête."""

    query: str
    cost_before: float
    evaluations: list[IndexEvaluation] = field(default_factory=list)
    combined_cost_after: float | None = None  # tous les index candidats ensemble
    combined_gain_pct: float | None = None
    accepted: list[IndexCandidate] = field(default_factory=list)
    min_gain_pct: float = MIN_GAIN_PCT

    @property
    def accepted_size_bytes(self) -> int:
        sizes = {e.candidate: e.size_bytes for e in self.evaluations}
        return sum(sizes.get(c, 0) for c in self.accepted)


def _gain(before: float, after: float) -> float:
    return round(100 * (before - after) / before, 1) if before > 0 else 0.0


def _index_names(plan: dict[str, Any]) -> set[str]:
    return {str(n["Index Name"]) for n, _ in walk(plan) if "Index Name" in n}


def _create(conn: Connection, candidate: IndexCandidate) -> tuple[int, str]:
    row = conn.execute(
        "SELECT indexrelid, indexname FROM hypopg_create_index(%s)", (candidate.ddl(),)
    ).fetchone()
    assert row is not None
    return int(row[0]), str(row[1])


def _size(conn: Connection, oid: int) -> int:
    row = conn.execute("SELECT hypopg_relation_size(%s)", (oid,)).fetchone()
    return int(row[0]) if row else 0


def evaluate(
    conn: Connection,
    query: str,
    candidates: list[IndexCandidate],
    min_gain_pct: float = MIN_GAIN_PCT,
) -> ValidationResult:
    """Mesure le gain de chaque index candidat, seul puis tous ensemble.

    Un index est retenu s'il est utilisé dans le plan « tous ensemble » et que ce
    plan est au moins `min_gain_pct` % moins coûteux. (Tester ensemble compte pour
    les jointures, où il faut parfois deux index pour changer de stratégie.)
    """
    conn.execute("SELECT hypopg_reset()")
    try:
        plan_before, _ = explain(conn, query)
        result = ValidationResult(
            query=query, cost_before=float(plan_before["Total Cost"]), min_gain_pct=min_gain_pct
        )
        if not candidates:
            return result

        # 1. Chaque index seul
        for cand in candidates:
            oid, name = _create(conn, cand)
            plan, _ = explain(conn, query)
            after = float(plan["Total Cost"])
            result.evaluations.append(
                IndexEvaluation(
                    candidate=cand,
                    cost_after=after,
                    gain_pct=_gain(result.cost_before, after),
                    used=name in _index_names(plan),
                    size_bytes=_size(conn, oid),
                )
            )
            conn.execute("SELECT hypopg_reset()")

        # 2. Tous ensemble
        names = {_create(conn, c)[1]: c for c in candidates}
        plan, _ = explain(conn, query)
        result.combined_cost_after = float(plan["Total Cost"])
        result.combined_gain_pct = _gain(result.cost_before, result.combined_cost_after)
        used = _index_names(plan)
        if result.combined_gain_pct >= min_gain_pct:
            result.accepted = [c for name, c in names.items() if name in used]
        return result
    finally:
        conn.execute("SELECT hypopg_reset()")  # ne jamais laisser d'index hypothétique
