"""Réécritures automatiques de requêtes (sans changer le résultat).

Pour l'instant : « colonne::date = jour » devient un intervalle, pour qu'un index
sur la colonne puisse servir. Les deux formes renvoient exactement les mêmes lignes.
"""

import re

_CAST_DATE_EQ = re.compile(
    r"(?P<col>\b\w+(?:\.\w+)?)::date\s*=\s*"
    r"(?P<day>.+?)"
    r"(?=\s+(?:AND|OR|GROUP\s+BY|ORDER\s+BY|LIMIT)\b|\s*\)|\s*;?\s*$)",
    re.IGNORECASE,
)


def rewrite_cast_date(query: str) -> str | None:
    """« created_at::date = X »  ->  « created_at >= (X) AND created_at < (X) + 1 ».

    Renvoie None si le motif n'est pas trouvé.
    """
    m = _CAST_DATE_EQ.search(query)
    if not m:
        return None
    col, day = m.group("col"), m.group("day").strip()
    replacement = f"{col} >= ({day}) AND {col} < ({day}) + 1"
    return query[: m.start()] + replacement + query[m.end() :]
