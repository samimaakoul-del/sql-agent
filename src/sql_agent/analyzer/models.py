"""Structures de données de l'analyseur."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IndexCandidate:
    """Un index qui pourrait aider. `columns` peut contenir une expression (ex. lower(email))."""

    table: str
    columns: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.table}({', '.join(self.columns)})"

    def ddl(self) -> str:
        """Ordre CREATE INDEX correspondant (une expression doit être entre parenthèses)."""
        cols = ", ".join(f"({c})" if "(" in c else c for c in self.columns)
        return f"CREATE INDEX ON {self.table} ({cols})"


@dataclass(frozen=True)
class Finding:
    """Un problème détecté dans le plan."""

    rule: str  # même vocabulaire que les causes du catalogue (workload.json)
    table: str | None
    message: str  # explication en français (utilisée aussi si le LLM est indisponible)
    candidate: IndexCandidate | None = None


@dataclass(frozen=True)
class TableInfo:
    """Métadonnées d'une table utiles aux règles."""

    rows: float
    columns: frozenset[str]
    indexed_leading_columns: frozenset[str]  # 1re colonne de chaque index existant


@dataclass
class Diagnosis:
    """Résultat complet de l'analyse d'une requête."""

    query: str
    analyzed_query: str  # requête réellement passée à EXPLAIN (après correction éventuelle)
    total_cost: float
    primary_cause: str | None
    findings: list[Finding] = field(default_factory=list)
    candidates: list[IndexCandidate] = field(default_factory=list)
    rewrite_hint: str | None = None
    rewritten_query: str | None = None  # réécriture automatique équivalente, si possible
    plan: dict[str, Any] = field(default_factory=dict)
