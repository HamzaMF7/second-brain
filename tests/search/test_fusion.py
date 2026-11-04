"""Reciprocal Rank Fusion : scores calculables de tête, 1 / (k + rang)."""

import pytest

from second_brain.search.fusion import rrf


def test_aucune_liste() -> None:
    assert rrf([], k=60) == []


def test_listes_vides() -> None:
    assert rrf([[], []], k=60) == []


def test_une_seule_liste_garde_son_ordre() -> None:
    fused = rrf([["a", "b", "c"]], k=60)
    assert [doc for doc, _ in fused] == ["a", "b", "c"]
    assert fused[0][1] == pytest.approx(1 / 61)
    assert fused[2][1] == pytest.approx(1 / 63)


def test_scores_additionnes_entre_listes() -> None:
    scores = dict(rrf([["a", "b"], ["b", "a"]], k=10))
    assert scores["a"] == pytest.approx(1 / 11 + 1 / 12)
    assert scores["b"] == pytest.approx(1 / 12 + 1 / 11)


def test_document_present_dans_une_seule_liste() -> None:
    scores = dict(rrf([["a", "b"], ["c"]], k=60))
    assert scores["b"] == pytest.approx(1 / 62)  # rien de la 2e liste, pas de pénalité
    assert scores["c"] == pytest.approx(1 / 61)


def test_exemple_de_la_tache_7_1() -> None:
    lexical = ["A", "B", "C", "D", "E"]
    semantic = ["C", "F", "A", "G", "B"]
    fused = rrf([lexical, semantic], k=60)
    assert [doc for doc, _ in fused] == ["A", "C", "B", "F", "D", "G", "E"]
    assert dict(fused)["B"] == pytest.approx(1 / 62 + 1 / 65)


def test_le_consensus_gagne_avec_k_grand() -> None:
    # x : 1er d'une seule liste ; y : 4e des deux.
    lists = [["x", "p", "q", "y"], ["r", "s", "t", "y"]]
    assert rrf(lists, k=60)[0][0] == "y"  # 2/64 > 1/61


def test_le_champion_gagne_avec_k_petit() -> None:
    lists = [["x", "p", "q", "y"], ["r", "s", "t", "y"]]
    order = [doc for doc, _ in rrf(lists, k=1)]
    assert order.index("x") < order.index("y")  # 1/2 > 2/5


def test_k_zero_accepte() -> None:
    assert rrf([["a"]], k=0) == [("a", 1.0)]


def test_k_negatif_refuse() -> None:
    with pytest.raises(ValueError, match="k"):
        rrf([["a"]], k=-1)


def test_egalite_departagee_par_le_meilleur_rang() -> None:
    # k = 1 : a (rangs 1 et 5) = 1/2 + 1/6 = 2/3 ; b (rangs 2 et 2) = 1/3 + 1/3 = 2/3.
    # Même score : a passe devant grâce à son meilleur rang (1 contre 2), quel que soit
    # l'ordre des listes.
    first = ["a", "b", "x", "y", "z"]
    second = ["p", "b", "q", "r", "a"]
    for lists in ([first, second], [second, first]):
        fused = rrf(lists, k=1)
        assert dict(fused)["a"] == dict(fused)["b"]
        assert [doc for doc, _ in fused][:2] == ["a", "b"]


def test_egalite_parfaite_departagee_par_l_ordre_des_listes() -> None:
    # a et c ont le même score et le même meilleur rang (1) : la 1re liste passe devant.
    fused = rrf([["a", "b", "c"], ["c", "b", "a"]], k=60)
    assert [doc for doc, _ in fused][:2] == ["a", "c"]
    fused = rrf([["c", "b", "a"], ["a", "b", "c"]], k=60)
    assert [doc for doc, _ in fused][:2] == ["c", "a"]


def test_doublon_dans_une_liste_compte_une_fois() -> None:
    scores = dict(rrf([["a", "b", "a"]], k=60))
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["b"] == pytest.approx(1 / 62)


def test_identifiants_entiers() -> None:
    assert [doc for doc, _ in rrf([[3, 1], [1, 2]], k=60)] == [1, 3, 2]


def test_resultat_deterministe() -> None:
    lists = [["a", "b", "c", "d"], ["d", "c", "b", "a"]]
    assert rrf(lists, k=60) == rrf(lists, k=60)


def test_poids_multiplient_chaque_contribution() -> None:
    scores = dict(rrf([["a"], ["b"]], k=60, weights=[2.0, 1.0]))
    assert scores["a"] == pytest.approx(2 / 61)
    assert scores["b"] == pytest.approx(1 / 61)


def test_poids_favorisent_une_liste() -> None:
    lists = [["a", "b"], ["b", "a"]]
    assert rrf(lists, k=60, weights=[2.0, 1.0])[0][0] == "a"
    assert rrf(lists, k=60, weights=[1.0, 2.0])[0][0] == "b"


def test_poids_egaux_a_un_comme_sans_poids() -> None:
    lists = [["a", "b", "c"], ["c", "d"]]
    assert rrf(lists, k=60, weights=[1.0, 1.0]) == rrf(lists, k=60)


def test_poids_nombre_incorrect_refuse() -> None:
    with pytest.raises(ValueError, match="poids"):
        rrf([["a"], ["b"]], k=60, weights=[1.0])


def test_poids_negatif_refuse() -> None:
    with pytest.raises(ValueError, match="poids"):
        rrf([["a"], ["b"]], k=60, weights=[1.0, -1.0])
