"""F2 - Règles de diagnostic appliquées à un plan EXPLAIN (format JSON).

Fonctions pures : elles ne touchent pas à la base, donc faciles à tester.
"""

import re
from collections.abc import Iterator
from typing import Any

from sql_agent.analyzer.models import Finding, IndexCandidate, TableInfo

LARGE_TABLE_ROWS = 10_000  # en dessous, un parcours complet est normal

# Ordre de priorité pour choisir la cause principale
PRIORITY = [
    "cast_empeche_index",
    "fonction_sur_colonne",
    "joker_en_tete",
    "jointure_inefficace",
    "tri_sans_index",
    "index_manquant",
]

_COL = r"(?:\w+\.)?(\w+)"  # colonne, éventuellement préfixée par un alias
_CAST = re.compile(rf"\(\s*{_COL}\s*\)::(\w+)")
_FUNC = re.compile(rf"\b(lower|upper|date_trunc|coalesce|trim|abs)\(\s*{_COL}\s*\)", re.I)
_LIKE = re.compile(rf"{_COL}\s*~~\*?\s*('(?:[^']|'')*'|\$\d+)")
_EQ = re.compile(rf"\(\s*{_COL}\s*=\s*")
_RANGE = re.compile(rf"\(\s*{_COL}\s*(?:>=|<=|>|<)\s*")
_JOIN = re.compile(r"\(\s*(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)\s*\)")

Node = dict[str, Any]


def walk(node: Node, parents: tuple[Node, ...] = ()) -> Iterator[tuple[Node, tuple[Node, ...]]]:
    """Parcourt l'arbre du plan : (nœud, ancêtres)."""
    yield node, parents
    for child in node.get("Plans", []):
        yield from walk(child, (*parents, node))


def relations(plan: Node) -> dict[str, str]:
    """Alias -> nom de table, pour tous les parcours de table du plan."""
    return {
        str(n.get("Alias") or n["Relation Name"]): str(n["Relation Name"])
        for n, _ in walk(plan)
        if "Relation Name" in n
    }


def _fmt(rows: float) -> str:
    """1000000 -> '1 000 000'."""
    return f"{int(rows):,}".replace(",", " ")


def _is_large(table: str, tables: dict[str, TableInfo]) -> bool:
    info = tables.get(table)
    return info is not None and info.rows >= LARGE_TABLE_ROWS


def _not_indexed(table: str, column: str, tables: dict[str, TableInfo]) -> bool:
    info = tables.get(table)
    return info is not None and column not in info.indexed_leading_columns


def _scan_below(node: Node) -> Node | None:
    """Premier parcours de table sous un nœud (en traversant Gather, Hash, Sort...)."""
    for n, _ in walk(node):
        if "Relation Name" in n:
            return n
    return None


def _filter_findings(scan: Node, table: str, tables: dict[str, TableInfo]) -> list[Finding]:
    """Règles sur le filtre (WHERE) d'un parcours complet de grande table."""
    filt: str = scan.get("Filter", "")
    if not filt:
        return []
    columns = tables[table].columns

    if (m := _CAST.search(filt)) and m.group(1) in columns:
        col, typ = m.group(1), m.group(2)
        return [
            Finding(
                "cast_empeche_index",
                table,
                f"La colonne {col} est convertie en {typ} (« {col}::{typ} ») : PostgreSQL doit "
                f"convertir chaque ligne et ne peut pas utiliser d'index sur {col}. "
                f"Réécrire la condition en intervalle sur {col}.",
                IndexCandidate(table, (col,)),
            )
        ]

    if (m := _FUNC.search(filt)) and m.group(2) in columns:
        func, col = m.group(1).lower(), m.group(2)
        return [
            Finding(
                "fonction_sur_colonne",
                table,
                f"La fonction {func}() est appliquée à la colonne {col} : un index classique "
                f"sur {col} est inutilisable. Il faut un index sur l'expression {func}({col}).",
                IndexCandidate(table, (f"{func}({col})",)),
            )
        ]

    if (m := _LIKE.search(filt)) and m.group(1) in columns:
        col, pattern = m.group(1), m.group(2)
        if pattern.startswith("'%") or pattern.startswith("$"):
            precision = (
                "Le motif commence par « % »"
                if pattern.startswith("'%")
                else "Si le motif commence par « % »"
            )
            return [
                Finding(
                    "joker_en_tete",
                    table,
                    f"{precision} : un index B-tree sur {col} ne peut pas aider (il trie par "
                    f"début de texte). Solutions : éviter le joker en tête, ou un index "
                    f"trigramme (extension pg_trgm).",
                    None,
                )
            ]

    eq = [c for c in _EQ.findall(filt) if c in columns]
    rng = [c for c in _RANGE.findall(filt) if c in columns and c not in eq]
    cols = tuple(dict.fromkeys(eq + rng))[:3]  # égalités d'abord, puis intervalles
    if cols and _not_indexed(table, cols[0], tables):
        return [
            Finding(
                "index_manquant",
                table,
                f"Parcours complet de {table} (~{_fmt(tables[table].rows)} lignes) pour "
                f"filtrer sur {', '.join(cols)} : aucun index ne permet d'aller directement "
                f"aux lignes utiles.",
                IndexCandidate(table, cols),
            )
        ]
    return []


def diagnose(plan: Node, tables: dict[str, TableInfo]) -> list[Finding]:
    """Applique toutes les règles et renvoie les problèmes trouvés."""
    aliases = relations(plan)
    findings: list[Finding] = []

    for node, parents in walk(plan):
        ntype = node["Node Type"]

        # 1. Parcours complet d'une grande table avec un filtre
        if ntype == "Seq Scan" and _is_large(node["Relation Name"], tables):
            findings += _filter_findings(node, node["Relation Name"], tables)

        # 2. Tri d'une grande table pour n'en garder que quelques lignes (ORDER BY ... LIMIT)
        if ntype in ("Sort", "Incremental Sort") and any(
            p["Node Type"] == "Limit" for p in parents
        ):
            scan = _scan_below(node)
            is_full_scan = scan is not None and scan["Node Type"] == "Seq Scan"
            if scan and is_full_scan and _is_large(scan["Relation Name"], tables):
                table = scan["Relation Name"]
                keys = [re.sub(r"^\w+\.|\s+(ASC|DESC).*$", "", k) for k in node.get("Sort Key", [])]
                keys = [k for k in keys if k in tables[table].columns]
                if keys and _not_indexed(table, keys[0], tables):
                    findings.append(
                        Finding(
                            "tri_sans_index",
                            table,
                            f"Pour renvoyer quelques lignes triées par {', '.join(keys)}, "
                            f"PostgreSQL lit et trie toute la table {table}. Un index sur "
                            f"{', '.join(keys)} fournit les lignes déjà triées "
                            f"(il peut être lu dans les deux sens, ASC ou DESC).",
                            IndexCandidate(table, tuple(keys)),
                        )
                    )

        # 3. Jointure où un côté est une grande table lue en entier
        cond = node.get("Hash Cond") or node.get("Merge Cond") or node.get("Join Filter")
        if cond and (m := _JOIN.search(cond)):
            for alias, col in ((m.group(1), m.group(2)), (m.group(3), m.group(4))):
                table = aliases.get(alias)
                if not table or not _is_large(table, tables):
                    continue
                side = next(
                    (
                        n
                        for n, _ in walk(node)
                        if n.get("Alias") == alias and n["Node Type"] == "Seq Scan"
                    ),
                    None,
                )
                if side and not side.get("Filter") and _not_indexed(table, col, tables):
                    findings.append(
                        Finding(
                            "jointure_inefficace",
                            table,
                            f"Jointure sur {table}.{col} sans index : toute la table {table} "
                            f"est lue pour retrouver les lignes correspondantes. Un index sur "
                            f"{table}({col}) permettrait d'aller les chercher directement.",
                            IndexCandidate(table, (col,)),
                        )
                    )
    return findings


def primary_cause(findings: list[Finding]) -> str | None:
    """Cause principale = règle la plus prioritaire parmi celles déclenchées."""
    rules = {f.rule for f in findings}
    return next((r for r in PRIORITY if r in rules), None)


def candidates(findings: list[Finding]) -> list[IndexCandidate]:
    """Index candidats, sans doublon, dans l'ordre des problèmes trouvés."""
    return list(dict.fromkeys(f.candidate for f in findings if f.candidate))
