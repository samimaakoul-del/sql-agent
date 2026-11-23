"""Tests du module d'évaluation (jeu de test, attaques, rapport)."""

import psycopg
import pytest

from sql_agent.db import connect
from sql_agent.demo.workload import DEFAULT_URL
from sql_agent.evaluation.run import (
    AttackResult,
    QueryResult,
    Report,
    evaluate_query,
    load_attacks,
    load_dataset,
    same_shape,
    to_markdown,
)

AGENT_URL = "postgresql://agent_ro:agent_ro@localhost:5433/shop"


def test_jeu_de_test_30_requetes_10_dev_20_test() -> None:
    data = load_dataset()
    assert len(data) == 30
    assert sum(split == "dev" for split, _ in data) == 10
    assert len({q.id for _, q in data}) == 30


def test_jeu_de_test_contient_des_pieges() -> None:
    pieges = [q for split, q in load_dataset() if split == "test" and q.cause is None]
    assert len(pieges) >= 5


def test_15_attaques_identifiants_uniques() -> None:
    attacks = load_attacks()
    assert len(attacks) == 15
    assert len({a["id"] for a in attacks}) == 15
    assert all(a["endpoint"] in {"analyze", "validate"} for a in attacks)


def test_meme_forme_normalisee() -> None:
    assert same_shape(
        "SELECT * FROM orders WHERE customer_id = 4242",
        "SELECT * FROM orders WHERE customer_id = $1",
    )
    assert not same_shape(
        "SELECT * FROM orders WHERE id = 1", "SELECT * FROM customers WHERE id = $1"
    )


def _qr(qid: str, split: str, ok: bool) -> QueryResult:
    return QueryResult(
        id=qid, split=split, sql="SELECT 1", expected_cause="index_manquant",
        found_cause="index_manquant" if ok else None, cause_ok=ok, expected_indexes=["t(a)"],
        accepted=["t(a)"] if ok else [], index_ok=ok, gain_pct=99.0 if ok else None,
        proposals=1, proposals_valid=1, seconds=0.01,
    )  # fmt: skip


def test_rapport_markdown() -> None:
    report = Report(
        label="TEST",
        date="2026-01-01 00:00",
        c1=(10, 10),
        queries=[_qr("S01", "dev", True), _qr("T01", "test", False)],
        attacks=[AttackResult("A01", "Suppression", 422, True, True, 0.1)],
    )
    md = to_markdown(report)
    assert "# Résultats de l'évaluation – TEST" in md
    assert "| C2 Diagnostic (bonne cause) | 1/1 (100 %) | 0/1 (0 %) | **1/2 (50 %)**" in md
    assert "**T01**" in md  # listée dans les erreurs à analyser
    assert "**1/1** (dont 1 refusées)" in md


def _base_disponible() -> bool:
    try:
        with psycopg.connect(DEFAULT_URL, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


@pytest.mark.skipif(not _base_disponible(), reason="base de démo non démarrée")
def test_evaluation_d_une_requete_piege() -> None:
    """T11 (clé primaire) : rien à signaler, rien à proposer."""
    t11 = next(q for split, q in load_dataset() if q.id == "T11")
    with connect(AGENT_URL) as conn:
        r = evaluate_query(conn, "test", t11)
    assert r.cause_ok and r.index_ok and r.accepted == []
