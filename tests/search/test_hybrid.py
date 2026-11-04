"""Recherche hybride : deux retrievers factices aux classements connus, fusion par RRF."""

from pathlib import Path

import pytest

from second_brain.config import SearchConfig
from second_brain.search.base import Retriever
from second_brain.search.hybrid import HybridRetriever
from second_brain.search.models import SearchResult


def chunk(chunk_id: int, snippet: str = "…", document_id: int | None = None) -> SearchResult:
    doc = document_id if document_id is not None else chunk_id
    return SearchResult(chunk_id, doc, Path(f"/doc{doc}.md"), 0.0, snippet)


class FakeRetriever(Retriever):
    """Renvoie une liste fixe (déjà triée) et note les tailles demandées."""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.requested: list[int] = []

    def search(self, query: str, k: int) -> list[SearchResult]:
        self.requested.append(k)
        return self.results[:k]


def hybrid(
    lexical: list[SearchResult], semantic: list[SearchResult], **config: int
) -> tuple[HybridRetriever, FakeRetriever, FakeRetriever]:
    lex, sem = FakeRetriever(lexical), FakeRetriever(semantic)
    return HybridRetriever(lex, sem, SearchConfig(**config)), lex, sem


def test_ordre_rrf_de_l_exemple_7_1() -> None:
    # A..G = chunks 1..7 ; lexical A B C D E, sémantique C F A G B.
    retriever, _, _ = hybrid(
        [chunk(i) for i in (1, 2, 3, 4, 5)], [chunk(i) for i in (3, 6, 1, 7, 2)]
    )

    results = retriever.search("q", 10)

    assert [r.chunk_id for r in results] == [1, 3, 2, 6, 4, 7, 5]
    assert results[0].score == pytest.approx(1 / 61 + 1 / 63)


def test_rangs_d_origine_conserves() -> None:
    retriever, _, _ = hybrid([chunk(1), chunk(2)], [chunk(3), chunk(1)])

    by_id = {r.chunk_id: r for r in retriever.search("q", 10)}

    assert (by_id[1].lexical_rank, by_id[1].semantic_rank) == (1, 2)
    assert (by_id[2].lexical_rank, by_id[2].semantic_rank) == (2, None)
    assert (by_id[3].lexical_rank, by_id[3].semantic_rank) == (None, 1)


def test_extrait_lexical_prefere_car_surligne() -> None:
    retriever, _, _ = hybrid(
        [chunk(1, "\x02mot\x03 trouvé")], [chunk(1, "premiers mots"), chunk(2, "autre")]
    )

    by_id = {r.chunk_id: r.snippet for r in retriever.search("q", 10)}

    assert by_id == {1: "\x02mot\x03 trouvé", 2: "autre"}


def test_k_coupe_la_liste_fusionnee() -> None:
    retriever, _, _ = hybrid([chunk(i) for i in range(1, 6)], [chunk(i) for i in range(6, 11)])

    assert len(retriever.search("q", 3)) == 3


def test_profondeur_des_candidats() -> None:
    retriever, lex, sem = hybrid([], [], hybrid_candidates=30)

    retriever.search("q", 10)
    retriever.search("q", 50)

    assert lex.requested == sem.requested == [30, 50]  # au moins k, pour pouvoir en rendre k


def test_k_de_rrf_vient_de_la_config() -> None:
    retriever, _, _ = hybrid([chunk(1)], [chunk(2)], rrf_k=10)

    assert retriever.search("q", 10)[0].score == pytest.approx(1 / 11)


def test_sans_vecteurs_reste_l_ordre_lexical() -> None:
    retriever, _, _ = hybrid([chunk(3), chunk(1), chunk(2)], [])

    assert [r.chunk_id for r in retriever.search("q", 10)] == [3, 1, 2]


def test_k_nul_n_interroge_personne() -> None:
    retriever, lex, sem = hybrid([chunk(1)], [chunk(1)])

    assert retriever.search("q", 0) == []
    assert lex.requested == sem.requested == []
