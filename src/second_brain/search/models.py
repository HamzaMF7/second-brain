"""Modèle des résultats de recherche, commun à toutes les méthodes."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Un passage trouvé. Convention du projet : plus le score est grand, meilleur il est."""

    chunk_id: int
    document_id: int
    path: Path
    score: float
    snippet: str  # extrait, termes trouvés entre SearchConfig.highlight_open / _close
    page: int | None = None
    section: str | None = None
    # Rempli au regroupement par document : chunks de ce document trouvés par BM25 (qui
    # contiennent donc des mots de la requête). Le sémantique n'y compte pas : il renvoie
    # toujours ses plus proches voisins, pertinents ou non.
    matched_chunks: int = 0
    # Rang du chunk dans la liste BM25 et dans la liste sémantique (None = absent).
    lexical_rank: int | None = None
    semantic_rank: int | None = None
