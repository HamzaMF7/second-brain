"""Métriques par question : valeurs calculables de tête."""

from collections.abc import Callable

import pytest
from metrics import hit_at_k, recall_at_k, reciprocal_rank

RANKED = ["a", "b", "c", "d", "e"]
Metric = Callable[..., float]


def test_hit_at_k() -> None:
    assert hit_at_k(RANKED, {"c"}, k=3) == 1.0
    assert hit_at_k(RANKED, {"c"}, k=2) == 0.0
    assert hit_at_k(RANKED, {"z"}, k=5) == 0.0


def test_recall_at_k_fraction_des_attendus() -> None:
    assert recall_at_k(RANKED, {"a", "d", "z", "y"}, k=5) == pytest.approx(2 / 4)
    assert recall_at_k(RANKED, {"a", "d", "z", "y"}, k=3) == pytest.approx(1 / 4)


def test_recall_plafonne_quand_il_y_a_plus_d_attendus_que_k() -> None:
    expected = {f"doc{i}" for i in range(20)}
    ranked = [f"doc{i}" for i in range(5)]

    assert recall_at_k(ranked, expected, k=5) == pytest.approx(5 / 20)  # le maximum possible


def test_reciprocal_rank_du_premier_attendu() -> None:
    assert reciprocal_rank(RANKED, {"c", "e"}, k=10) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKED, {"a"}, k=10) == 1.0


def test_reciprocal_rank_nul_au_dela_de_k_ou_absent() -> None:
    assert reciprocal_rank(RANKED, {"e"}, k=4) == 0.0
    assert reciprocal_rank(RANKED, {"z"}, k=10) == 0.0


def test_liste_vide() -> None:
    assert hit_at_k([], {"a"}, k=5) == 0.0
    assert recall_at_k([], {"a"}, k=5) == 0.0
    assert reciprocal_rank([], {"a"}, k=5) == 0.0


def test_doublons_comptes_une_fois() -> None:
    # Un document renvoyé deux fois ne compte qu'une fois, mais occupe bien deux places.
    assert recall_at_k(["a", "a", "b"], {"a", "b"}, k=2) == pytest.approx(1 / 2)
    assert recall_at_k(["a", "a", "b"], {"a", "b"}, k=3) == pytest.approx(2 / 2)


@pytest.mark.parametrize("metric", [hit_at_k, recall_at_k, reciprocal_rank])
def test_aucun_attendu_refuse(metric: Metric) -> None:
    with pytest.raises(ValueError, match="attendu"):
        metric(RANKED, set(), k=5)


@pytest.mark.parametrize("metric", [hit_at_k, recall_at_k, reciprocal_rank])
def test_k_non_positif_refuse(metric: Metric) -> None:
    with pytest.raises(ValueError, match="k"):
        metric(RANKED, {"a"}, k=0)
