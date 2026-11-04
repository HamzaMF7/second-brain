"""Recherche hybride : candidats lexicaux et sémantiques fusionnés par RRF."""

from collections.abc import Callable
from dataclasses import replace

from second_brain.config import SearchConfig
from second_brain.search.base import Retriever
from second_brain.search.fusion import rrf
from second_brain.search.grouping import group_by_document
from second_brain.search.models import SearchResult


class HybridRetriever(Retriever):
    """Fusionne deux retrievers sur les rangs seulement : leurs scores ne sont pas comparables.

    `config.fusion` :
    - "chunk" : RRF sur les chunks. Un même document trouvé par deux chunks différents (un
      par méthode) ne reçoit pas de bonus de consensus ;
    - "document" : chaque liste est d'abord réduite au meilleur chunk de chaque document,
      puis RRF porte sur les documents (un résultat par document, rangs de document).
    """

    def __init__(
        self, lexical: Retriever, semantic: Retriever, config: SearchConfig | None = None
    ) -> None:
        self.lexical = lexical
        self.semantic = semantic
        self.config = config or SearchConfig()

    def search(self, query: str, k: int) -> list[SearchResult]:
        if k <= 0:
            return []
        depth = max(self.config.hybrid_candidates, k)
        lexical = self.lexical.search(query, depth)
        semantic = self.semantic.search(query, depth)
        if self.config.fusion == "document":
            lexical, semantic = group_by_document(lexical), group_by_document(semantic)
            return self._fuse(lexical, semantic, k, key=lambda r: r.document_id)
        return self._fuse(lexical, semantic, k, key=lambda r: r.chunk_id)

    def _fuse(
        self,
        lexical: list[SearchResult],
        semantic: list[SearchResult],
        k: int,
        key: Callable[[SearchResult], int],
    ) -> list[SearchResult]:
        lexical_ranks = {key(r): rank for rank, r in enumerate(lexical, start=1)}
        semantic_ranks = {key(r): rank for rank, r in enumerate(semantic, start=1)}
        # Résultat affiché : celui de la liste lexicale s'il existe (termes surlignés).
        by_key = {key(r): r for r in semantic} | {key(r): r for r in lexical}
        fused = rrf(
            [[key(r) for r in lexical], [key(r) for r in semantic]],
            k=self.config.rrf_k,
            weights=self.config.rrf_weights,
        )
        return [
            replace(
                by_key[item],
                score=score,
                lexical_rank=lexical_ranks.get(item),
                semantic_rank=semantic_ranks.get(item),
            )
            for item, score in fused[:k]
        ]
