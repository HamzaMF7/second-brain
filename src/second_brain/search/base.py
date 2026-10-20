"""Contrat commun aux méthodes de recherche (lexicale, vectorielle, hybride)."""

from abc import ABC, abstractmethod

from second_brain.search.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    def search(self, query: str, k: int) -> list[SearchResult]:
        """Les k meilleurs passages pour la requête, du meilleur au moins bon."""
