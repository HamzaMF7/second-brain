"""Test avec un vrai modèle (téléchargé au premier lancement) : exclu par défaut et en CI.

Lancer avec : uv run pytest -m model
"""

import math

import pytest

from second_brain.config import EmbeddingConfig
from second_brain.embeddings.fastembed_embedder import FastEmbedEmbedder

pytestmark = pytest.mark.model


def cosine(a: list[float], b: list[float]) -> float:
    # Vecteurs normalisés : le cosinus est le produit scalaire.
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize("model_name", ["minishlab/potion-multilingual-128M"])
def test_deux_phrases_proches_une_eloignee(model_name: str) -> None:
    embedder = FastEmbedEmbedder(EmbeddingConfig(model_name=model_name))
    chat, chaton, banque = embedder.embed_passages(
        [
            "Le chat dort sur le canapé du salon.",
            "Un chaton fait la sieste sur le sofa.",
            "La banque centrale relève ses taux d'intérêt.",
        ]
    )

    assert len(chat) == embedder.dimension
    assert cosine(chat, chaton) > cosine(chat, banque)
    assert cosine(chat, chaton) > cosine(chaton, banque)
