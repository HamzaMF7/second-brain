"""Recherche lexicale BM25 via SQLite FTS5."""

import sqlite3
from pathlib import Path

from second_brain.config import SearchConfig
from second_brain.search.base import Retriever
from second_brain.search.models import SearchResult
from second_brain.search.query import to_fts5_query

# `rank` vaut bm25(chunks_fts) : NÉGATIF, plus petit = meilleur, pour qu'un ORDER BY
# croissant mette les meilleurs en premier (et ORDER BY rank est optimisé par FTS5).
# On expose -rank : dans tout le projet, un score plus grand est meilleur.
# snippet(..., 1, ...) : colonne `text` (la colonne 0, `context`, n'est jamais affichée).
_SQL = """
SELECT c.id, c.document_id, d.path, -chunks_fts.rank,
       snippet(chunks_fts, 1, ?, ?, ?, ?), c.page, c.section
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN documents d ON d.id = c.document_id
WHERE chunks_fts MATCH ?
ORDER BY chunks_fts.rank
LIMIT ?
"""


class LexicalRetriever(Retriever):
    def __init__(self, conn: sqlite3.Connection, config: SearchConfig | None = None) -> None:
        self.conn = conn
        self.config = config or SearchConfig()

    def search(self, query: str, k: int) -> list[SearchResult]:
        fts_query = to_fts5_query(query)
        if fts_query is None or k <= 0:
            return []
        c = self.config
        rows = self.conn.execute(
            _SQL,
            (c.highlight_open, c.highlight_close, c.ellipsis, c.snippet_tokens, fts_query, k),
        ).fetchall()
        return [
            SearchResult(
                chunk_id=chunk_id,
                document_id=document_id,
                path=Path(path),
                score=score,
                snippet=snippet,
                page=page,
                section=section,
            )
            for chunk_id, document_id, path, score, snippet, page, section in rows
        ]
