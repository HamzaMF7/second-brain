"""Reciprocal Rank Fusion : fusionne des classements en n'utilisant que les rangs.

score(d) = Σ 1 / (k + rang de d dans chaque liste), rang à partir de 1. Un document absent
d'une liste n'en reçoit rien. Les scores d'origine (BM25, cosinus) sont ignorés : leurs
échelles ne sont pas comparables.
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass


@dataclass(slots=True)
class _Entry:
    score: float
    best_rank: int
    first_seen: int  # ordre de première apparition, listes lues dans l'ordre donné


def rrf[T: Hashable](rankings: Sequence[Sequence[T]], *, k: int) -> list[tuple[T, float]]:
    """(élément, score RRF) du meilleur au moins bon.

    Égalités départagées par le meilleur rang obtenu dans une liste, puis par l'ordre de
    première apparition (la première liste passe devant). Un doublon dans une même liste
    ne compte qu'à sa première position.
    """
    if k < 0:
        raise ValueError(f"k doit être positif ou nul (reçu {k})")
    entries: dict[T, _Entry] = {}
    for ranking in rankings:
        seen: set[T] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            contribution = 1 / (k + rank)
            entry = entries.get(item)
            if entry is None:
                entries[item] = _Entry(contribution, rank, len(entries))
            else:
                entry.score += contribution
                entry.best_rank = min(entry.best_rank, rank)
    ordered = sorted(
        entries.items(), key=lambda kv: (-kv[1].score, kv[1].best_rank, kv[1].first_seen)
    )
    return [(item, entry.score) for item, entry in ordered]
