"""Contrat commun aux modèles d'embeddings."""

from abc import ABC, abstractmethod


class Embedder(ABC):
    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifie le modèle et sa façon de l'appeler, stocké avec chaque vecteur :
        s'il change, les vecteurs concernés sont recalculés."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Nombre de composantes de chaque vecteur."""

    @abstractmethod
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Vecteurs normalisés des passages à indexer, dans l'ordre reçu."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Vecteur normalisé d'une requête (préfixe éventuellement différent des passages)."""
