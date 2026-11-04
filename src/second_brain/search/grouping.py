"""Regroupement des résultats par document : on ne garde que le meilleur chunk de chacun."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

from second_brain.search.base import Retriever
from second_brain.search.models import SearchResult


def group_by_document(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Premier (donc meilleur) résultat de chaque document, dans l'ordre reçu.

    `matched_chunks` : nombre de chunks du document parmi `results` trouvés par BM25.
    """
    counts = Counter(r.document_id for r in results if r.lexical_rank is not None)
    seen: set[int] = set()
    grouped: list[SearchResult] = []
    for result in results:
        if result.document_id not in seen:
            seen.add(result.document_id)
            grouped.append(replace(result, matched_chunks=counts[result.document_id]))
    return grouped


def search_documents(
    retriever: Retriever, query: str, k: int, fetch_factor: int = 5
) -> list[SearchResult]:
    """Les k meilleurs documents distincts.

    Un long document peut occuper beaucoup de places parmi les chunks : on en demande
    `fetch_factor × k`, puis on double tant qu'il manque des documents et que le retriever
    en a encore (il en renvoie moins que demandé quand il n'y en a plus).
    """
    if k <= 0:
        return []
    limit = k * fetch_factor
    while True:
        results = retriever.search(query, limit)
        documents = group_by_document(results)
        if len(documents) >= k or len(results) < limit:
            return documents[:k]
        limit *= 2
