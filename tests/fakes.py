"""Doublures de test partagées (importables grâce à pythonpath = ["tests"])."""

from second_brain.embeddings.base import Embedder


class FakeEmbedder(Embedder):
    """Embedder déterministe sans modèle : enregistre chaque lot reçu.

    `fail_on_call` : numéro (à partir de 1) de l'appel qui lève une erreur, pour simuler
    un modèle qui plante en cours d'indexation.
    `query_vector` : vecteur renvoyé pour toute requête (sinon calculé comme un passage).
    """

    def __init__(
        self,
        model_id: str = "faux#1",
        fail_on_call: int | None = None,
        query_vector: list[float] | None = None,
    ) -> None:
        self._model_id = model_id
        self.fail_on_call = fail_on_call
        self.query_vector = query_vector
        self.batches: list[list[str]] = []
        self.queries: list[str] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return 2

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(texts)
        if self.fail_on_call == len(self.batches):
            raise RuntimeError("modèle en panne")
        return [[1.0, float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self.query_vector if self.query_vector is not None else [1.0, float(len(text))]

    @property
    def embedded_texts(self) -> list[str]:
        return [text for batch in self.batches for text in batch]
