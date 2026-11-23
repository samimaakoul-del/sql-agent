"""Tests du collecteur F1 et de la route /slow-queries."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from sql_agent.api.main import app, get_connection
from sql_agent.collector import fetch_slow_queries
from sql_agent.db import connect
from sql_agent.demo.workload import DEFAULT_URL, load_catalog, run_workload

AGENT_URL = "postgresql://agent_ro:agent_ro@localhost:5433/shop"

# --- Fausse connexion pour tester sans base ---

FAKE_ROW = {
    "queryid": 1,
    "query": "SELECT *   FROM orders\n WHERE customer_id = $1",
    "calls": 5,
    "total_ms": 138.812,
    "mean_ms": 27.76,
    "rows": 50,
    "share_pct": 12.34,
}


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, *args: object) -> "FakeCursor":
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def cursor(self, **kwargs: object) -> FakeCursor:
        return FakeCursor(self.rows)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def _use_fake(rows: list[dict[str, Any]]) -> None:
    app.dependency_overrides[get_connection] = lambda: FakeConnection(rows)


# --- Tests unitaires ---


def test_fetch_normalise_les_espaces_et_arrondit() -> None:
    [q] = fetch_slow_queries(FakeConnection([FAKE_ROW]))  # type: ignore[arg-type]
    assert q.query == "SELECT * FROM orders WHERE customer_id = $1"
    assert q.total_ms == 138.81
    assert q.share_pct == 12.3


def test_fetch_refuse_un_tri_inconnu() -> None:
    with pytest.raises(ValueError):
        fetch_slow_queries(FakeConnection([]), order_by="query; DROP TABLE x")  # type: ignore[arg-type]


def test_fetch_refuse_une_limite_hors_bornes() -> None:
    with pytest.raises(ValueError):
        fetch_slow_queries(FakeConnection([]), limit=1000)  # type: ignore[arg-type]


def test_route_renvoie_le_top(client: TestClient) -> None:
    _use_fake([FAKE_ROW])
    resp = client.get("/slow-queries?limit=5&order_by=mean")
    assert resp.status_code == 200
    assert resp.json()[0]["calls"] == 5


def test_route_liste_vide(client: TestClient) -> None:
    _use_fake([])
    assert client.get("/slow-queries").json() == []


def test_route_refuse_un_tri_invalide(client: TestClient) -> None:
    _use_fake([])
    assert client.get("/slow-queries?order_by=hack").status_code == 422


def test_route_base_injoignable_renvoie_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise psycopg.OperationalError("connexion refusée")

    monkeypatch.setattr("sql_agent.api.main.connect", boom)
    resp = client.get("/slow-queries")
    assert resp.status_code == 503
    assert "injoignable" in resp.json()["detail"]


# --- Tests d'intégration (nécessitent : docker compose up -d db) ---


def _base_disponible() -> bool:
    try:
        with psycopg.connect(DEFAULT_URL, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


integration = pytest.mark.skipif(not _base_disponible(), reason="base de démo non démarrée")


@integration
def test_les_10_requetes_lentes_sont_dans_le_top_15() -> None:
    """Critère C1 de la fiche de cadrage."""
    run_workload(DEFAULT_URL)
    with connect(AGENT_URL) as conn:
        top = fetch_slow_queries(conn, limit=15)
    lentes = [q for q in load_catalog() if q.slow]
    # pg_stat_statements remplace les constantes : on compare le début de chaque requête
    trouvees = [s for s in lentes if any(_meme_forme(s.sql, t.query) for t in top)]
    assert len(trouvees) == 10, f"manquantes : {[s.id for s in lentes if s not in trouvees]}"


@integration
def test_les_requetes_de_l_agent_sont_exclues() -> None:
    with connect(AGENT_URL) as conn:
        fetch_slow_queries(conn)
        top = fetch_slow_queries(conn, limit=100)
    # « share_pct » n'apparaît que dans la requête du collecteur (exécutée par agent_ro)
    assert not any("share_pct" in q.query for q in top)


@integration
def test_la_connexion_de_l_agent_ne_peut_pas_ecrire() -> None:
    """Garde-fou F6 : même un ordre d'écriture est refusé."""
    with connect(AGENT_URL) as conn, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("CREATE TABLE pirate (id int)")


def _meme_forme(original: str, normalisee: str) -> bool:
    """Compare jusqu'à la première constante (remplacée par $1 dans pg_stat_statements)."""
    prefixe = original.split("'")[0].split("=")[0].strip()
    return normalisee.startswith(prefixe[:40])
