"""Tests de l'analyseur F2 (règles sur plans EXPLAIN) et de la route /analyze."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from sql_agent.analyzer import AnalysisError, IndexCandidate, analyze
from sql_agent.analyzer.explain import _TYPED_PARAM, check_is_single_select
from sql_agent.analyzer.models import TableInfo
from sql_agent.analyzer.rules import candidates, diagnose, primary_cause
from sql_agent.api.main import app, get_connection
from sql_agent.db import connect
from sql_agent.demo.workload import DEFAULT_URL, load_catalog

AGENT_URL = "postgresql://agent_ro:agent_ro@localhost:5433/shop"

# --- Métadonnées et plans de test (copiés de vrais plans PostgreSQL 16) ---

TABLES = {
    "orders": TableInfo(
        1_000_000,
        frozenset({"id", "customer_id", "status", "created_at", "total"}),
        frozenset({"id"}),
    ),
    "customers": TableInfo(
        100_000,
        frozenset({"id", "email", "full_name", "country", "created_at"}),
        frozenset({"id"}),
    ),
    "order_items": TableInfo(
        2_500_000,
        frozenset({"id", "order_id", "product_id", "quantity", "unit_price"}),
        frozenset({"id"}),
    ),
    "products": TableInfo(5_000, frozenset({"id", "name", "category", "price"}), frozenset({"id"})),
}


def scan(table: str, filt: str | None = None, alias: str | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {
        "Node Type": "Seq Scan",
        "Relation Name": table,
        "Alias": alias or table,
        "Total Cost": 100.0,
    }
    if filt:
        node["Filter"] = filt
    return node


def gather(*children: dict[str, Any]) -> dict[str, Any]:
    return {"Node Type": "Gather", "Total Cost": 200.0, "Plans": list(children)}


def run(plan: dict[str, Any]) -> tuple[str | None, list[str]]:
    findings = diagnose(plan, TABLES)
    return primary_cause(findings), [str(c) for c in candidates(findings)]


# --- Règles ---


def test_index_manquant_sur_filtre_egalite() -> None:
    assert run(gather(scan("orders", "(customer_id = $1)"))) == (
        "index_manquant",
        ["orders(customer_id)"],
    )


def test_index_composite_egalite_puis_intervalle() -> None:
    filt = "((status = 'pending'::text) AND (created_at >= (now() - '7 days'::interval)))"
    assert run(gather(scan("orders", filt))) == (
        "index_manquant",
        ["orders(status, created_at)"],
    )


def test_petite_table_ignoree() -> None:
    # 5 000 lignes : un parcours complet est normal
    assert run(scan("products", "(category = $1)")) == (None, [])


def test_colonne_deja_indexee_ignoree() -> None:
    assert run(scan("orders", "(id = $1)")) == (None, [])


def test_fonction_sur_colonne() -> None:
    assert run(scan("customers", "(lower(email) = 'a@b.c'::text)")) == (
        "fonction_sur_colonne",
        ["customers(lower(email))"],
    )


def test_cast_empeche_index() -> None:
    assert run(gather(scan("orders", "((created_at)::date = (CURRENT_DATE - 30))"))) == (
        "cast_empeche_index",
        ["orders(created_at)"],
    )


@pytest.mark.parametrize("pattern", ["'%9999@example.com'::text", "$1"])
def test_joker_en_tete_ne_propose_aucun_index(pattern: str) -> None:
    assert run(scan("customers", f"(email ~~ {pattern})")) == ("joker_en_tete", [])


def test_like_sans_joker_en_tete_n_est_pas_un_joker() -> None:
    cause, _ = run(scan("customers", "(email ~~ 'client1%'::text)"))
    assert cause != "joker_en_tete"


def test_tri_sans_index_sous_limit() -> None:
    plan = {
        "Node Type": "Limit",
        "Total Cost": 1.0,
        "Plans": [
            {
                "Node Type": "Gather Merge",
                "Total Cost": 1.0,
                "Plans": [
                    {
                        "Node Type": "Sort",
                        "Total Cost": 1.0,
                        "Sort Key": ["created_at DESC"],
                        "Plans": [scan("orders")],
                    }
                ],
            }
        ],
    }
    assert run(plan) == ("tri_sans_index", ["orders(created_at)"])


def test_jointure_sur_cle_etrangere_non_indexee() -> None:
    plan = gather(
        {
            "Node Type": "Hash Join",
            "Total Cost": 1.0,
            "Hash Cond": "(oi.order_id = o.id)",
            "Plans": [
                scan("order_items", alias="oi"),
                {
                    "Node Type": "Hash",
                    "Total Cost": 1.0,
                    "Plans": [scan("orders", "(customer_id = $1)", alias="o")],
                },
            ],
        }
    )
    cause, cands = run(plan)
    assert cause == "jointure_inefficace"
    assert set(cands) == {"order_items(order_id)", "orders(customer_id)"}


# --- Outils ---


def test_ddl_index_expression() -> None:
    assert IndexCandidate("customers", ("lower(email)",)).ddl() == (
        "CREATE INDEX ON customers ((lower(email)))"
    )


def test_reecriture_interval_parametre() -> None:
    q = "SELECT 1 FROM t WHERE d >= now() - interval $2"
    assert _TYPED_PARAM.sub(r"\2::\1", q) == "SELECT 1 FROM t WHERE d >= now() - $2::interval"


@pytest.mark.parametrize(
    "query",
    ["", "DELETE FROM orders", "DROP TABLE orders", "SELECT 1; DROP TABLE orders", "  ;  "],
)
def test_controle_refuse_ce_qui_n_est_pas_un_select(query: str) -> None:
    with pytest.raises(AnalysisError):
        check_is_single_select(query)


def test_controle_accepte_select_et_with() -> None:
    assert check_is_single_select("SELECT 1;") == "SELECT 1"
    assert check_is_single_select("with x as (select 1) select * from x")


def test_correspondance_index_alternative_acceptable() -> None:
    s03 = next(q for q in load_catalog() if q.id == "S03")
    assert s03.indexes_match({"orders(created_at)"})
    assert s03.indexes_match({"orders(status, created_at)"})
    assert not s03.indexes_match({"orders(status)"})


# --- Route API ---


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_route_refuse_une_ecriture_avec_422(client: TestClient) -> None:
    app.dependency_overrides[get_connection] = lambda: None  # jamais utilisée
    resp = client.post("/analyze", json={"sql": "DELETE FROM orders"})
    assert resp.status_code == 422
    assert "lecture" in resp.json()["detail"]


# --- Intégration : diagnostic des 10 requêtes lentes du catalogue (critère C2) ---


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
def test_diagnostic_du_catalogue(q: Any) -> None:
    with connect(AGENT_URL) as conn:
        d = analyze(conn, q.sql)
    assert d.primary_cause == q.cause
    assert q.indexes_match({str(c) for c in d.candidates})


@integration
def test_requete_normalisee_avec_interval_corrigee() -> None:
    sql = "SELECT count(*) FROM orders WHERE status = $1 AND created_at >= now() - interval $2"
    with connect(AGENT_URL) as conn:
        d = analyze(conn, sql)
    assert "$2::interval" in d.analyzed_query
    assert d.primary_cause == "index_manquant"


@integration
def test_requete_normalisee_non_planifiable_message_clair() -> None:
    with connect(AGENT_URL) as conn, pytest.raises(AnalysisError, match="vraies valeurs"):
        analyze(conn, "SELECT count(*) FROM orders WHERE created_at::date = current_date - $1")
