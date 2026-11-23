"""Tests du catalogue de requêtes et du générateur de trafic."""

import json
from importlib import resources

import psycopg
import pytest

from sql_agent.demo.workload import DEFAULT_URL, load_catalog, run_workload


def _causes_connues() -> set[str]:
    raw = resources.files("sql_agent.demo").joinpath("workload.json").read_text("utf-8")
    return set(json.loads(raw)["causes"])


# --- Tests unitaires (sans base) ---


def test_catalogue_contient_10_requetes_lentes() -> None:
    lentes = [q for q in load_catalog() if q.slow]
    assert len(lentes) == 10


def test_identifiants_uniques() -> None:
    ids = [q.id for q in load_catalog()]
    assert len(ids) == len(set(ids))


def test_chaque_requete_lente_est_annotee() -> None:
    causes = _causes_connues()
    for q in load_catalog():
        if q.slow:
            assert q.cause in causes, f"{q.id} : cause inconnue {q.cause!r}"


def test_catalogue_ne_contient_que_des_select() -> None:
    # Le générateur ne doit jamais modifier les données
    for q in load_catalog():
        assert q.sql.lstrip().upper().startswith("SELECT"), q.id


# --- Test d'intégration (nécessite la base Docker : docker compose up -d db) ---


def _base_disponible() -> bool:
    try:
        with psycopg.connect(DEFAULT_URL, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


@pytest.mark.skipif(not _base_disponible(), reason="base de démo non démarrée")
def test_requetes_lentes_apparaissent_dans_pg_stat_statements() -> None:
    run_workload(DEFAULT_URL, slow_repeat=1, fast_repeat=1)
    with psycopg.connect(DEFAULT_URL) as conn:
        row = conn.execute(
            "SELECT count(*) FROM pg_stat_statements WHERE query LIKE %s",
            ("%FROM orders WHERE customer_id%",),
        ).fetchone()
    assert row is not None and row[0] >= 1
