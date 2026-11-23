"""Évaluation de l'agent sur le jeu de test : critères C1 à C6 de la fiche de cadrage.

Lancer (local)  :  python -m sql_agent.evaluation --label L2
Lancer (Docker) :  docker compose run --rm evaluate

Deux connexions :
  - AGENT (agent_ro, lecture seule) : tout ce que fait l'agent ;
  - ADMIN : seulement pour générer le trafic (C1) et vérifier l'état de la base (C5).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from sql_agent.analyzer import AnalysisError, analyze
from sql_agent.analyzer.explain import table_info
from sql_agent.analyzer.rules import relations
from sql_agent.collector import fetch_slow_queries
from sql_agent.db import connect
from sql_agent.demo.workload import CatalogQuery, load_catalog, run_workload
from sql_agent.validator import InvalidIndexError, ValidationResult, evaluate, parse_index_ddl

AGENT_URL = os.getenv("DATABASE_URL", "postgresql://agent_ro:agent_ro@localhost:5433/shop")
ADMIN_URL = os.getenv("WORKLOAD_DATABASE_URL", "postgresql://admin:admin@localhost:5433/shop")

TARGETS = {  # cibles L2 / L3 de la fiche de cadrage
    "C1": (7 / 10, 10 / 10),
    "C2": (0.60, 0.85),
    "C3": (0.50, 0.80),
    "C4": (0.80, 0.95),
    "C5": (1.0, 1.0),
}
C6_TARGETS = (60.0, 30.0)  # secondes


# ---------------------------------------------------------------- jeu de test


def load_dataset() -> list[tuple[str, CatalogQuery]]:
    """Split « dev » (catalogue, a servi à écrire les règles) + split « test » (nouveau)."""
    raw = resources.files("sql_agent.evaluation").joinpath("dataset.json").read_text("utf-8")
    test = [CatalogQuery(**q) for q in json.loads(raw)["queries"]]
    dev = [q for q in load_catalog() if q.slow]
    return [("dev", q) for q in dev] + [("test", q) for q in test]


def load_attacks() -> list[dict[str, Any]]:
    raw = resources.files("sql_agent.evaluation").joinpath("attacks.json").read_text("utf-8")
    attacks: list[dict[str, Any]] = json.loads(raw)["attacks"]
    return attacks


# ---------------------------------------------------------------- C2, C3, C4, C6


@dataclass
class QueryResult:
    id: str
    split: str
    sql: str
    expected_cause: str | None
    found_cause: str | None
    cause_ok: bool
    expected_indexes: list[str]
    accepted: list[str]
    index_ok: bool
    gain_pct: float | None
    proposals: int
    proposals_valid: int
    seconds: float
    note: str | None = None
    error: str | None = None


def _proposal_is_valid(conn: psycopg.Connection[tuple[Any, ...]], ddl: str, tables: Any) -> bool:
    """C4 : la proposition passe le contrôle strict ET PostgreSQL l'accepte (via HypoPG)."""
    try:
        parse_index_ddl(ddl, tables)
        conn.execute("SELECT * FROM hypopg_create_index(%s)", (ddl,))
        return True
    except (InvalidIndexError, psycopg.Error):
        return False
    finally:
        conn.execute("SELECT hypopg_reset()")


def evaluate_query(
    conn: psycopg.Connection[tuple[Any, ...]], split: str, q: CatalogQuery
) -> QueryResult:
    start = time.perf_counter()
    try:
        d = analyze(conn, q.sql)
        results: list[ValidationResult] = [evaluate(conn, d.analyzed_query, d.candidates)]
        if d.rewritten_query:
            results.append(evaluate(conn, d.rewritten_query, d.candidates))
        seconds = time.perf_counter() - start
        best = max(results, key=lambda r: r.combined_gain_pct or 0)
        accepted = [str(c) for c in best.accepted]
        tables = table_info(conn, set(relations(d.plan).values()))
        valid = sum(_proposal_is_valid(conn, c.ddl(), tables) for c in d.candidates)
        return QueryResult(
            id=q.id, split=split, sql=q.sql,
            expected_cause=q.cause, found_cause=d.primary_cause,
            cause_ok=d.primary_cause == q.cause,
            expected_indexes=q.expected_indexes + [f"(ou) {a}" for a in q.acceptable_indexes],
            accepted=accepted, index_ok=q.indexes_match(set(accepted)),
            gain_pct=best.combined_gain_pct if best.accepted else None,
            proposals=len(d.candidates), proposals_valid=valid,
            seconds=round(seconds, 3), note=q.note,
        )  # fmt: skip
    except AnalysisError as exc:
        return QueryResult(
            id=q.id, split=split, sql=q.sql, expected_cause=q.cause, found_cause=None,
            cause_ok=False, expected_indexes=q.expected_indexes, accepted=[], index_ok=False,
            gain_pct=None, proposals=0, proposals_valid=0,
            seconds=round(time.perf_counter() - start, 3), note=q.note, error=str(exc),
        )  # fmt: skip


# ---------------------------------------------------------------- C1


def same_shape(original: str, normalized: str) -> bool:
    """pg_stat_statements remplace les constantes par $1 : on compare le début."""
    prefix = original.split("'")[0].split("=")[0].strip()
    return normalized.startswith(prefix[:40])


def measure_c1() -> tuple[int, int]:
    run_workload(ADMIN_URL)
    with connect(AGENT_URL) as conn:
        top = fetch_slow_queries(conn, limit=15)
    slow = [q for q in load_catalog() if q.slow]
    found = sum(any(same_shape(s.sql, t.query) for t in top) for s in slow)
    return found, len(slow)


# ---------------------------------------------------------------- C5


@dataclass
class AttackResult:
    id: str
    description: str
    status_code: int
    refused: bool  # l'agent a dit non (4xx)
    db_unchanged: bool  # la base est identique : attaque bloquée
    seconds: float


_SNAPSHOT = """
SELECT
  (SELECT array_agg(relname || ':' || relkind::text ORDER BY relname)
     FROM pg_class WHERE relnamespace = 'public'::regnamespace),
  (SELECT count(*) FROM customers), (SELECT count(*) FROM orders),
  (SELECT count(*) FROM order_items), (SELECT count(*) FROM products),
  (SELECT min(email) FROM customers)
"""


def _snapshot() -> tuple[Any, ...]:
    with psycopg.connect(ADMIN_URL) as conn:
        row = conn.execute(_SNAPSHOT).fetchone()
    assert row is not None
    return tuple(row)


def measure_c5() -> list[AttackResult]:
    from sql_agent.api.main import app  # import tardif : l'API lit DATABASE_URL

    client = TestClient(app, raise_server_exceptions=False)
    results = []
    for a in load_attacks():
        before = _snapshot()
        start = time.perf_counter()
        if a["endpoint"] == "validate":
            resp = client.post("/validate", json={"sql": a["sql"], "indexes": a["indexes"]})
            refused = resp.status_code >= 400 or bool(resp.json().get("rejected_indexes"))
        else:
            resp = client.post("/analyze", json={"sql": a["sql"]})
            refused = resp.status_code >= 400
        seconds = time.perf_counter() - start
        results.append(
            AttackResult(
                id=a["id"],
                description=a["description"],
                status_code=resp.status_code,
                refused=refused,
                db_unchanged=_snapshot() == before,
                seconds=round(seconds, 2),
            )  # fmt: skip
        )
    return results


# ---------------------------------------------------------------- rapport


@dataclass
class Report:
    label: str
    date: str
    c1: tuple[int, int]
    queries: list[QueryResult] = field(default_factory=list)
    attacks: list[AttackResult] = field(default_factory=list)


def _ratio(ok: int, total: int) -> str:
    return f"{ok}/{total} ({100 * ok / total:.0f} %)" if total else "–"


def _target(name: str, value: float) -> str:
    l2, l3 = TARGETS[name]
    return "✅ L3" if value >= l3 else ("🟡 L2" if value >= l2 else "❌")


def to_markdown(r: Report) -> str:
    def by(split: str | None) -> list[QueryResult]:
        return [q for q in r.queries if split is None or q.split == split]

    def c2(qs: list[QueryResult]) -> tuple[int, int]:
        return sum(q.cause_ok for q in qs), len(qs)

    def c3(qs: list[QueryResult]) -> tuple[int, int]:
        return sum(q.index_ok for q in qs), len(qs)

    props = sum(q.proposals for q in r.queries)
    valid = sum(q.proposals_valid for q in r.queries)
    times = [q.seconds for q in r.queries]
    blocked = sum(a.db_unchanged for a in r.attacks)
    refused = sum(a.refused for a in r.attacks)
    c6_med, c6_max = statistics.median(times), max(times)

    lines = [
        f"# Résultats de l'évaluation – {r.label}",
        "",
        f"*Généré automatiquement le {r.date} par `python -m sql_agent.evaluation`.*",
        "",
        "- **dev** = 10 requêtes du catalogue, connues pendant l'écriture des règles.",
        "- **test** = 20 requêtes nouvelles, annotées sans regarder l'outil (dont 5 pièges).",
        "- Agent évalué : règles + HypoPG (le LLM n'est pas encore branché).",
        "",
        "## Synthèse",
        "",
        "| Critère | dev | test | **total** | Cible L2 / L3 | Atteint |",
        "|---|---|---|---|---|---|",
    ]
    c1_ok, c1_n = r.c1
    lines.append(f"| C1 Détection (10 lentes dans le top 15) | – | – | **{c1_ok}/{c1_n}** "
                 f"| 7/10 / 10/10 | {_target('C1', c1_ok / c1_n)} |")  # fmt: skip
    for name, fn, label in (("C2", c2, "Diagnostic (bonne cause)"), ("C3", c3, "Index utile")):
        ok, n = fn(by(None))
        l2, l3 = TARGETS[name]
        lines.append(
            f"| {name} {label} | {_ratio(*fn(by('dev')))} | {_ratio(*fn(by('test')))} "
            f"| **{_ratio(ok, n)}** | {l2:.0%} / {l3:.0%} | {_target(name, ok / n)} |"
        )
    lines.append(f"| C4 SQL proposé valide | – | – | **{_ratio(valid, props)}** | 80 % / 95 % "
                 f"| {_target('C4', valid / props) if props else '–'} |")  # fmt: skip
    lines.append(f"| C5 Attaques bloquées | – | – | **{blocked}/{len(r.attacks)}** "
                 f"(dont {refused} refusées) | 100 % | {_target('C5', blocked / len(r.attacks))} |")  # fmt: skip
    c6_ok = "✅ L3" if c6_max < C6_TARGETS[1] else ("🟡 L2" if c6_max < C6_TARGETS[0] else "❌")
    lines.append(f"| C6 Temps d'analyse | – | – | **médiane {c6_med:.2f} s, max {c6_max:.2f} s** "
                 f"| < 60 s / < 30 s | {c6_ok} |")  # fmt: skip

    lines += ["", "## Détail par requête", "",
              "| Id | Split | Cause attendue | Cause trouvée | Index attendus | Index retenus | Gain | OK |",
              "|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for q in r.queries:
        marks = ("✅" if q.cause_ok else "❌") + ("✅" if q.index_ok else "❌")
        gain = f"{q.gain_pct:.0f} %" if q.gain_pct is not None else "–"
        lines.append(
            f"| {q.id} | {q.split} | {q.expected_cause or '(aucune)'} | "
            f"{q.found_cause or ('erreur' if q.error else '(aucune)')} | "
            f"{'<br>'.join(q.expected_indexes) or '(aucun)'} | {'<br>'.join(q.accepted) or '(aucun)'} "
            f"| {gain} | {marks} |"
        )

    errors = [q for q in r.queries if not (q.cause_ok and q.index_ok)]
    lines += ["", "## Erreurs à analyser", ""]
    if not errors:
        lines.append("Aucune.")
    for q in errors:
        lines.append(f"- **{q.id}** `{q.sql}`")
        lines.append(f"  - attendu : {q.expected_cause or '(aucune)'} / {q.expected_indexes or '(aucun)'} "
                     f"— obtenu : {q.found_cause or '(aucune)'} / {q.accepted or '(aucun)'}")  # fmt: skip
        if q.error:
            lines.append(f"  - erreur : {q.error}")
        if q.note:
            lines.append(f"  - note : {q.note}")

    lines += ["", "## Attaques (C5)", "", "| Id | Attaque | Réponse | Refusée | Base intacte | Durée |",
              "|---|---|---|---|---|---|"]  # fmt: skip
    for a in r.attacks:
        lines.append(f"| {a.id} | {a.description} | HTTP {a.status_code} | "
                     f"{'oui' if a.refused else '**non**'} | {'✅' if a.db_unchanged else '❌'} "
                     f"| {a.seconds:.2f} s |")  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> Report:
    parser = argparse.ArgumentParser(description="Évalue l'agent (critères C1 à C6).")
    parser.add_argument("--label", default="L2", help="étiquette du rapport (ex. L2, L3)")
    parser.add_argument("--out", default="results", help="dossier de sortie")
    args = parser.parse_args(argv)

    report = Report(
        label=args.label, date=datetime.now().strftime("%Y-%m-%d %H:%M"), c1=measure_c1()
    )
    with connect(AGENT_URL) as conn:
        report.queries = [evaluate_query(conn, split, q) for split, q in load_dataset()]
    report.attacks = measure_c5()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = to_markdown(report)
    (out / f"resultats_{args.label}.md").write_text(md, encoding="utf-8")
    (out / f"resultats_{args.label}.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(md)
    return report


if __name__ == "__main__":
    main()
