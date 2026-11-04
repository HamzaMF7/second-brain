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


def test_poids_de_la_config() -> None:
    retriever, _, _ = hybrid([chunk(1), chunk(2)], [chunk(2), chunk(1)])
    retriever.config = SearchConfig(rrf_weights=(2.0, 1.0))

    assert [r.chunk_id for r in retriever.search("q", 10)] == [1, 2]


def test_fusion_par_document_donne_le_bonus_de_consensus() -> None:
    # Document 1 : chunk 10 trouvé par BM25 (rang 2), chunk 11 par le sens (rang 2).
    # Document 2 : chunk 20, 1er de BM25 seulement. Document 3 : chunk 30, 1er du sens.
    lexical = [chunk(20, document_id=2), chunk(10, "\x02lex\x03", document_id=1)]
    semantic = [chunk(30, document_id=3), chunk(11, "sens", document_id=1)]
    by_chunk, _, _ = hybrid(lexical, semantic)
    by_document, _, _ = hybrid(lexical, semantic)
    by_document.config = SearchConfig(fusion="document")

    # Par chunk : 10 et 11 sont deux chunks différents, aucun consensus.
    assert by_chunk.search("q", 10)[0].document_id in {2, 3}
    # Par document : 1/62 + 1/62 > 1/61, le document 1 passe devant.
    results = by_document.search("q", 10)
    assert [r.document_id for r in results] == [1, 2, 3]
    first = results[0]
    assert (first.chunk_id, first.snippet) == (10, "\x02lex\x03")  # chunk lexical, surligné
    assert (first.lexical_rank, first.semantic_rank) == (2, 2)  # rangs de document


def test_fusion_par_document_garde_le_meilleur_chunk_de_chaque_liste() -> None:
    lexical = [chunk(10, document_id=1), chunk(11, document_id=1), chunk(20, document_id=2)]
    retriever, _, _ = hybrid(lexical, [])
    retriever.config = SearchConfig(fusion="document")

    results = retriever.search("q", 10)

    assert [(r.document_id, r.chunk_id, r.lexical_rank) for r in results] == [
        (1, 10, 1),
        (2, 20, 2),
    ]
