"""Recherche hybride : candidats lexicaux et sémantiques fusionnés par RRF, chunk par chunk."""

from dataclasses import replace

from second_brain.config import SearchConfig
from second_brain.search.base import Retriever
from second_brain.search.fusion import rrf
from second_brain.search.models import SearchResult


class HybridRetriever(Retriever):
    """Fusionne deux retrievers sur les rangs seulement : leurs scores ne sont pas comparables.

    Un même document trouvé par deux chunks différents (un par méthode) ne reçoit pas de
    bonus de consensus : la fusion se fait par chunk, le regroupement par document après.
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
        lexical_ranks = {r.chunk_id: rank for rank, r in enumerate(lexical, start=1)}
        semantic_ranks = {r.chunk_id: rank for rank, r in enumerate(semantic, start=1)}
        # Extrait lexical prioritaire : ses termes trouvés sont surlignés.
        by_chunk = {r.chunk_id: r for r in semantic} | {r.chunk_id: r for r in lexical}
        fused = rrf(
            [[r.chunk_id for r in lexical], [r.chunk_id for r in semantic]], k=self.config.rrf_k
        )
        return [
            replace(
                by_chunk[chunk_id],
                score=score,
                lexical_rank=lexical_ranks.get(chunk_id),
                semantic_rank=semantic_ranks.get(chunk_id),
            )
            for chunk_id, score in fused[:k]
        ]
