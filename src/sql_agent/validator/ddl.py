"""Contrôle strict d'un ordre CREATE INDEX proposé (par exemple par le LLM).

On n'accepte que la forme simple « CREATE INDEX [nom] ON table (col, ...) »,
avec des colonnes qui existent vraiment. Tout le reste est refusé : c'est ce
texte qui sera ensuite passé à HypoPG, puis montré à l'humain pour validation.
"""

import re

from sql_agent.analyzer.models import IndexCandidate, TableInfo

_DDL = re.compile(
    r"^\s*create\s+index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?(?:\w+\s+)?"
    r"on\s+(?:public\.)?(?P<table>\w+)\s*(?:using\s+btree\s*)?"
    r"\((?P<cols>.+)\)\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_PLAIN_COL = re.compile(r"^(\w+)(?:\s+(?:asc|desc))?$", re.IGNORECASE)
_EXPR_COL = re.compile(r"^\(?\s*(lower|upper)\(\s*(\w+)\s*\)\s*\)?$", re.IGNORECASE)


class InvalidIndexError(ValueError):
    """Ordre CREATE INDEX refusé ; le message explique pourquoi."""


def parse_index_ddl(ddl: str, tables: dict[str, TableInfo]) -> IndexCandidate:
    """Transforme un CREATE INDEX en IndexCandidate, ou lève InvalidIndexError."""
    m = _DDL.match(ddl)
    if not m:
        raise InvalidIndexError(
            f"Forme non reconnue (attendu : CREATE INDEX ON table (col)) : {ddl!r}"
        )
    table = m.group("table").lower()
    if table not in tables:
        raise InvalidIndexError(f"Table inconnue : {table}")
    known = tables[table].columns

    columns: list[str] = []
    for raw in m.group("cols").split(","):
        part = raw.strip()
        if plain := _PLAIN_COL.match(part):
            col = plain.group(1).lower()
            if col not in known:
                raise InvalidIndexError(f"Colonne inconnue : {table}.{col}")
            columns.append(col)
        elif expr := _EXPR_COL.match(part):
            func, col = expr.group(1).lower(), expr.group(2).lower()
            if col not in known:
                raise InvalidIndexError(f"Colonne inconnue : {table}.{col}")
            columns.append(f"{func}({col})")
        else:
            raise InvalidIndexError(f"Colonne ou expression non autorisée : {part!r}")
    if not 1 <= len(columns) <= 3:
        raise InvalidIndexError("Un index doit porter sur 1 à 3 colonnes.")
    return IndexCandidate(table, tuple(columns))
