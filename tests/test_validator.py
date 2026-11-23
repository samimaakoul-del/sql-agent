"""Tests du validateur F5 (HypoPG), du contrôle des CREATE INDEX et de la réécriture."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from sql_agent.analyzer import analyze
from sql_agent.analyzer.models import TableInfo
from sql_agent.analyzer.rewrite import rewrite_cast_date
from sql_agent.api.main import app
from sql_agent.db import connect
from sql_agent.demo.workload import DEFAULT_URL, load_catalog
from sql_agent.validator import InvalidIndexError, evaluate, parse_index_ddl

AGENT_URL = "postgresql://agent_ro:agent_ro@localhost:5433/shop"
TABLES = {
    "orders": TableInfo(1e6, frozenset({"id", "customer_id", "status", "created_at"}), frozenset()),
    "customers": TableInfo(1e5, frozenset({"id", "email"}), frozenset()),
}

# --- Contrôle des CREATE INDEX (ex. proposés par le LLM) ---


@pytest.mark.parametrize(
    ("ddl", "expected"),
    [
        ("CREATE INDEX ON orders (customer_id)", "orders(customer_id)"),
        (
            "create index idx_x on public.orders(status, created_at DESC);",
            "orders(status, created_at)",
        ),
        (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS i ON orders USING btree (customer_id)",
            "orders(customer_id)",
        ),
        ("CREATE INDEX ON customers ((lower(email)))", "customers(lower(email))"),
    ],
)
def test_ddl_accepte(ddl: str, expected: str) -> None:
    assert str(parse_index_ddl(ddl, TABLES)) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        "DROP TABLE orders",
        "CREATE INDEX ON orders (customer_id); DROP TABLE orders",
        "CREATE INDEX ON pirate (id)",  # table inconnue
        "CREATE INDEX ON orders (inexistante)",  # colonne inventée par le LLM
        "CREATE INDEX ON orders ((pg_sleep(10)))",  # expression non autorisée
        "CREATE INDEX ON orders (id, customer_id, status, created_at)",  # trop de colonnes
        "CREATE UNIQUE INDEX ON orders (customer_id)",
    ],
)
def test_ddl_refuse(ddl: str) -> None:
    with pytest.raises(InvalidIndexError):
        parse_index_ddl(ddl, TABLES)


# --- Réécriture ---


def test_reecriture_cast_date() -> None:
    q = "SELECT count(*) FROM orders WHERE created_at::date = current_date - 30"
    assert rewrite_cast_date(q) == (
        "SELECT count(*) FROM orders WHERE created_at >= (current_date - 30) "
        "AND created_at < (current_date - 30) + 1"
    )


def test_reecriture_cast_date_suivi_d_une_condition() -> None:
    q = "SELECT * FROM orders o WHERE o.created_at::date = '2026-01-15' AND status = 'x'"
    assert rewrite_cast_date(q) == (
        "SELECT * FROM orders o WHERE o.created_at >= ('2026-01-15') "
        "AND o.created_at < ('2026-01-15') + 1 AND status = 'x'"
    )


def test_pas_de_reecriture_sans_cast() -> None:
    assert rewrite_cast_date("SELECT * FROM orders WHERE id = 1") is None


# --- Intégration (nécessite : docker compose up -d db) ---


def _base_disponible() -> bool:
    try:
        with psycopg.connect(DEFAULT_URL, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


integration = pytest.mark.skipif(not _base_disponible(), reason="base de démo non démarrée")
SLOW = [q for q in load_catalog() if q.slow]


@integration
@pytest.mark.parametrize("q", SLOW, ids=[q.id for q in SLOW])
def test_index_retenus_par_hypopg(q: Any) -> None:
    """Critère C3 : les index retenus (gain >= 30 %) correspondent à l'annotation."""
    with connect(AGENT_URL) as conn:
        d = analyze(conn, q.sql)
        results = [evaluate(conn, d.analyzed_query, d.candidates)]
        if d.rewritten_query:
            results.append(evaluate(conn, d.rewritten_query, d.candidates))
    best = max(results, key=lambda r: r.combined_gain_pct or 0)
    assert q.indexes_match({str(c) for c in best.accepted})


@integration
def test_jointure_il_faut_tester_les_index_ensemble() -> None:
    """S06 : un des deux index seul est sous le seuil, mais ensemble ils sont retenus."""
    s06 = next(q for q in SLOW if q.id == "S06")
    with connect(AGENT_URL) as conn:
        d = analyze(conn, s06.sql)
        r = evaluate(conn, d.analyzed_query, d.candidates)
    assert min(e.gain_pct for e in r.evaluations) < r.min_gain_pct
    assert (r.combined_gain_pct or 0) >= r.min_gain_pct
    assert len(r.accepted) == 2


@integration
def test_aucun_index_reel_ni_hypothetique_ne_reste() -> None:
    """Garde-fou : la validation ne laisse aucune trace dans la base."""
    with connect(AGENT_URL) as conn:
        d = analyze(conn, SLOW[0].sql)
        evaluate(conn, d.analyzed_query, d.candidates)
        hypo = conn.execute("SELECT count(*) FROM hypopg_list_indexes").fetchone()
        real = conn.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'"
        ).fetchone()
    assert hypo is not None and hypo[0] == 0
    assert real is not None and real[0] == 4  # les 4 clés primaires


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)


@integration
def test_route_validate_avec_index_proposes(client: TestClient) -> None:
    body = {
        "sql": "SELECT * FROM orders WHERE customer_id = 42",
        "indexes": [
            "CREATE INDEX ON orders (customer_id)",  # utile
            "CREATE INDEX ON orders (status)",  # inutile ici
            "DROP TABLE orders",  # refusé
        ],
    }
    resp = client.post("/validate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["original"]["accepted"] == ["CREATE INDEX ON orders (customer_id)"]
    assert [r["ddl"] for r in data["rejected_indexes"]] == ["DROP TABLE orders"]
    assert "valider par un humain" in data["recommendation"]


@integration
def test_route_validate_joker_aucun_index(client: TestClient) -> None:
    resp = client.post("/validate", json={"sql": "SELECT id FROM customers WHERE email LIKE '%x'"})
    assert resp.json()["recommendation"] == "Aucun index classique ne peut aider cette requête."
