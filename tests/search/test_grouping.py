from pathlib import Path

from second_brain.search.base import Retriever
from second_brain.search.grouping import group_by_document, search_documents
from second_brain.search.models import SearchResult


def result(
    document_id: int, chunk_id: int, score: float, lexical_rank: int | None = 1
) -> SearchResult:
    path = Path(f"/doc{document_id}.md")
    return SearchResult(chunk_id, document_id, path, score, "…", lexical_rank=lexical_rank)


class FakeRetriever(Retriever):
    """Renvoie une liste fixe de chunks (triés) et note les tailles demandées."""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.requested: list[int] = []

    def search(self, query: str, k: int) -> list[SearchResult]:
        self.requested.append(k)
        return self.results[:k]


def test_group_by_document_garde_le_meilleur_chunk_dans_l_ordre() -> None:
    results = [result(1, 10, 9.0), result(1, 11, 8.0), result(2, 20, 7.0), result(1, 12, 6.0)]

    assert [(r.document_id, r.chunk_id) for r in group_by_document(results)] == [(1, 10), (2, 20)]


def test_group_by_document_compte_les_chunks_trouves() -> None:
    results = [result(1, 10, 9.0), result(2, 20, 8.0), result(1, 11, 7.0), result(1, 12, 6.0)]

    assert [(r.document_id, r.matched_chunks) for r in group_by_document(results)] == [
        (1, 3),
        (2, 1),
    ]


def test_group_by_document_ne_compte_pas_les_chunks_trouves_par_le_sens_seul() -> None:
    results = [result(1, 10, 9.0), result(1, 11, 8.0, lexical_rank=None), result(2, 20, 7.0, None)]

    assert [(r.document_id, r.matched_chunks) for r in group_by_document(results)] == [
        (1, 1),
        (2, 0),
    ]


def test_search_documents_renvoie_k_documents_distincts() -> None:
    retriever = FakeRetriever([result(d, d * 10, 10.0 - d) for d in range(1, 9)])

    assert [r.document_id for r in search_documents(retriever, "q", k=3)] == [1, 2, 3]


def test_search_documents_demande_plus_de_chunks_si_un_document_les_monopolise() -> None:
    # Le document 1 occupe les 40 premières places ; les documents 2 et 3 viennent après.
    chunks = [result(1, i, 100.0 - i) for i in range(40)] + [
        result(2, 200, 1.0),
        result(3, 300, 0.5),
    ]
    retriever = FakeRetriever(chunks)

    found = search_documents(retriever, "q", k=3, fetch_factor=5)

    assert [r.document_id for r in found] == [1, 2, 3]
    assert retriever.requested == [15, 30, 60]  # 3 × 5, puis doublé jusqu'à suffire


def test_search_documents_s_arrete_quand_il_n_y_a_plus_de_resultats() -> None:
    retriever = FakeRetriever([result(1, 1, 2.0), result(1, 2, 1.0)])

    assert [r.document_id for r in search_documents(retriever, "q", k=5)] == [1]
    assert retriever.requested == [25]  # moins de résultats que demandé : inutile d'insister


def test_search_documents_k_nul() -> None:
    assert search_documents(FakeRetriever([result(1, 1, 1.0)]), "q", k=0) == []
