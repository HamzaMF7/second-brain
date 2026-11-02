"""Recherche sémantique : similarité cosinus via sqlite-vec, en force brute."""

import sqlite3
from pathlib import Path

from second_brain.config import SearchConfig
from second_brain.embeddings.base import Embedder
from second_brain.search.base import Retriever
from second_brain.search.models import SearchResult
from second_brain.storage.vectors import serialize

# vec_distance_cosine renvoie 1 − cosinus (0 = même direction) ; on expose le cosinus
# lui-même, entre −1 et 1 : dans tout le projet, un score plus grand est meilleur.
# Filtre sur model_id : comparer des vecteurs de deux modèles n'a pas de sens (et leurs
# dimensions peuvent différer).
_SQL = """
SELECT c.id, c.document_id, d.path, 1 - vec_distance_cosine(v.embedding, ?) AS score,
       c.text, c.page, c.section
FROM chunk_vectors v
JOIN chunks c ON c.id = v.chunk_id
JOIN documents d ON d.id = c.document_id
WHERE v.model_id = ?
ORDER BY score DESC
LIMIT ?
"""


class SemanticRetriever(Retriever):
    def __init__(
        self, conn: sqlite3.Connection, embedder: Embedder, config: SearchConfig | None = None
    ) -> None:
        self.conn = conn
        self.embedder = embedder
        self.config = config or SearchConfig()

    def search(self, query: str, k: int) -> list[SearchResult]:
        if not query.strip() or k <= 0:
            return []
        vector = serialize(self.embedder.embed_query(query))
        rows = self.conn.execute(_SQL, (vector, self.embedder.model_id, k)).fetchall()
        return [
            SearchResult(
                chunk_id=chunk_id,
                document_id=document_id,
                path=Path(path),
                score=score,
                snippet=self._snippet(text),
                page=page,
                section=section,
            )
            for chunk_id, document_id, path, score, text, page, section in rows
        ]

    def _snippet(self, text: str) -> str:
        """Premiers mots du chunk : aucun terme à surligner, le sens ne se localise pas."""
        words = text.split()
        n = self.config.snippet_tokens
        return " ".join(words[:n]) + (self.config.ellipsis if len(words) > n else "")
