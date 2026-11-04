"""Métriques de recherche pour UNE question : liste classée de documents contre attendus.

Les moyennes sur un jeu de questions (MRR = moyenne des rangs réciproques) se font à part.
Un document renvoyé deux fois ne compte qu'une fois, mais occupe bien ses deux places.
"""

from collections.abc import Collection, Sequence


def _check(expected: Collection[str], k: int) -> None:
    if not expected:
        raise ValueError("aucun document attendu : question impossible à évaluer")
    if k <= 0:
        raise ValueError(f"k doit être strictement positif (reçu {k})")


def hit_at_k(ranked: Sequence[str], expected: Collection[str], k: int) -> float:
    """1 si au moins un attendu figure dans les k premiers, sinon 0."""
    _check(expected, k)
    return float(any(doc in expected for doc in ranked[:k]))


def recall_at_k(ranked: Sequence[str], expected: Collection[str], k: int) -> float:
    """Part des attendus présents dans les k premiers (plafonnée à k / nombre d'attendus)."""
    _check(expected, k)
    return len(set(ranked[:k]) & set(expected)) / len(expected)


def reciprocal_rank(ranked: Sequence[str], expected: Collection[str], k: int) -> float:
    """1 / rang du premier attendu parmi les k premiers, 0 s'il n'y en a aucun."""
    _check(expected, k)
    for rank, doc in enumerate(ranked[:k], start=1):
        if doc in expected:
            return 1 / rank
    return 0.0
