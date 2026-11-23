"""Générateur de trafic : simule une application qui envoie ses requêtes à la base.

Les requêtes lentes du catalogue apparaissent ensuite dans pg_stat_statements,
où l'agent (F1) doit les retrouver.

Lancer (Docker) :   docker compose run --rm workload
Lancer (local)  :   python -m sql_agent.demo.workload --help

Ce script utilise un compte ADMIN (il joue « l'application ») : il ne fait pas
partie de l'agent, qui lui n'utilise que le rôle lecture seule agent_ro.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from importlib import resources

import psycopg

DEFAULT_URL = "postgresql://admin:admin@localhost:5433/shop"


@dataclass(frozen=True)
class CatalogQuery:
    """Une requête du catalogue, avec son annotation si elle est lente."""

    id: str
    sql: str
    slow: bool
    cause: str | None = None
    expected_indexes: list[str] = field(default_factory=list)  # tous nécessaires
    acceptable_indexes: list[str] = field(default_factory=list)  # un seul suffit
    expected_rewrite: str | None = None

    def indexes_match(self, proposed: set[str]) -> bool:
        """Les index proposés correspondent-ils à l'annotation ?

        - aucun index attendu (ex. LIKE '%...') : rien ne doit être proposé ;
        - sinon : tous les index attendus, ou au moins une alternative acceptable.
        """
        if not self.expected_indexes:
            return not proposed
        return set(self.expected_indexes) <= proposed or bool(
            set(self.acceptable_indexes) & proposed
        )


def load_catalog() -> list[CatalogQuery]:
    """Charge le catalogue livré avec le paquet (workload.json)."""
    raw = resources.files("sql_agent.demo").joinpath("workload.json").read_text("utf-8")
    data = json.loads(raw)
    return [CatalogQuery(**q) for q in data["queries"]]


def run_workload(
    url: str,
    slow_repeat: int = 5,
    fast_repeat: int = 200,
    reset: bool = True,
) -> dict[str, float]:
    """Exécute le catalogue et renvoie le temps moyen (ms) de chaque requête.

    reset=True vide d'abord pg_stat_statements, pour que le classement ne
    reflète que ce trafic (et pas le chargement initial des données).
    """
    catalog = load_catalog()
    timings: dict[str, float] = {}
    with psycopg.connect(url, autocommit=True) as conn:
        if reset:
            conn.execute("SELECT pg_stat_statements_reset()")
        for q in catalog:
            repeat = slow_repeat if q.slow else fast_repeat
            start = time.perf_counter()
            for _ in range(repeat):
                conn.execute(q.sql).fetchall()
            timings[q.id] = (time.perf_counter() - start) * 1000 / repeat
    return timings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Génère du trafic SQL sur la base de démo.")
    parser.add_argument("--url", default=os.getenv("WORKLOAD_DATABASE_URL", DEFAULT_URL))
    parser.add_argument("--slow-repeat", type=int, default=5)
    parser.add_argument("--fast-repeat", type=int, default=200)
    parser.add_argument(
        "--no-reset", action="store_true", help="ne pas vider pg_stat_statements avant"
    )
    args = parser.parse_args(argv)

    timings = run_workload(args.url, args.slow_repeat, args.fast_repeat, reset=not args.no_reset)
    slow_ids = {q.id for q in load_catalog() if q.slow}
    print(f"{'Requête':<8} {'Type':<7} {'Temps moyen':>12}")
    for qid, ms in sorted(timings.items(), key=lambda kv: -kv[1]):
        kind = "lente" if qid in slow_ids else "rapide"
        print(f"{qid:<8} {kind:<7} {ms:>9.1f} ms")


if __name__ == "__main__":
    main()
