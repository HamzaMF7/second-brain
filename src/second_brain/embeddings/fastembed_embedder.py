"""Embedder fondé sur fastembed (ONNX Runtime, sans PyTorch)."""

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from second_brain.config import EmbeddingConfig
from second_brain.embeddings.base import Embedder
from second_brain.embeddings.specs import get_spec


class TextModel(Protocol):
    """Ce qu'on utilise de fastembed.TextEmbedding (remplaçable dans les tests)."""

    def embed(self, documents: Sequence[str], batch_size: int) -> Iterable[NDArray[Any]]:
        """Un vecteur par texte, dans l'ordre (type numérique variable selon le modèle)."""
        ...


ModelFactory = Callable[[str, Path], TextModel]


def load_fastembed_model(model_name: str, cache_dir: Path) -> TextModel:
    # Import tardif : charger fastembed et ONNX Runtime coûte environ une seconde,
    # inutile pour les commandes qui ne calculent pas d'embeddings.
    from fastembed import TextEmbedding

    return TextEmbedding(model_name, cache_dir=str(cache_dir))


class FastEmbedEmbedder(Embedder):
    def __init__(
        self, config: EmbeddingConfig, model_factory: ModelFactory = load_fastembed_model
    ) -> None:
        self.config = config
        self.spec = get_spec(config.model_name)  # modèle inconnu : erreur dès la construction
        self._factory = model_factory
        self._model: TextModel | None = None  # chargé au premier calcul (plusieurs Go en RAM)

    @property
    def model_id(self) -> str:
        return f"{self.spec.name}#{self.spec.signature}"

    @property
    def dimension(self) -> int:
        return self.spec.dimension

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self.spec.passage_prefix + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.spec.query_prefix + text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            self._model = self._factory(self.spec.name, self.config.cache_dir)
        vectors = np.array(
            list(self._model.embed(texts, batch_size=self.config.batch_size)), dtype=np.float32
        )
        # Certains modèles (e5) sortent des vecteurs non normalisés : on normalise toujours,
        # sans effet sur ceux qui le sont déjà. Un vecteur nul reste nul.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized: list[list[float]] = (vectors / norms).tolist()
        return normalized
