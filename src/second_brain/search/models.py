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
