"""Tests rapides de FastEmbedEmbedder, sans réseau : le vrai modèle est remplacé par un faux."""

import math
from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from second_brain.config import EmbeddingConfig, default_model_cache_dir
from second_brain.embeddings.base import Embedder
from second_brain.embeddings.fastembed_embedder import FastEmbedEmbedder
from second_brain.embeddings.specs import MODEL_SPECS, UnknownModelError, get_spec

E5 = "intfloat/multilingual-e5-large"
POTION = "minishlab/potion-multilingual-128M"


class FakeModel:
    """Enregistre ce qu'il reçoit ; renvoie (longueur du texte, 0, 3), non normalisé."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []

    def embed(self, documents: Sequence[str], batch_size: int) -> Iterable[NDArray[np.float32]]:
        self.calls.append((list(documents), batch_size))
        for text in documents:
            yield np.array([len(text), 0.0, 3.0], dtype=np.float32)


class FakeFactory:
    def __init__(self) -> None:
        self.model = FakeModel()
        self.loads: list[tuple[str, Path]] = []

    def __call__(self, model_name: str, cache_dir: Path) -> FakeModel:
        self.loads.append((model_name, cache_dir))
        return self.model


def embedder(model_name: str = E5, batch_size: int = 32) -> tuple[FastEmbedEmbedder, FakeFactory]:
    factory = FakeFactory()
    config = EmbeddingConfig(
        model_name=model_name, batch_size=batch_size, cache_dir=Path("/cache/models")
    )
    return FastEmbedEmbedder(config, model_factory=factory), factory


# --- Table des modèles --------------------------------------------------------------------


def test_modele_inconnu_refuse_explicitement() -> None:
    with pytest.raises(UnknownModelError, match="bge-inconnu"):
        get_spec("BAAI/bge-inconnu")


def test_modele_inconnu_refuse_des_la_construction() -> None:
    with pytest.raises(UnknownModelError):
        embedder("BAAI/bge-inconnu")


def test_les_trois_candidats_sont_dans_la_table() -> None:
    assert {E5, "google/embeddinggemma-300m", POTION} <= MODEL_SPECS.keys()


def test_signature_change_avec_les_prefixes() -> None:
    e5 = get_spec(E5)
    autre = type(e5)(e5.name, e5.dimension, query_prefix="", passage_prefix=e5.passage_prefix)

    assert autre.signature != e5.signature


# --- Embedder -----------------------------------------------------------------------------


def test_respecte_le_contrat_embedder() -> None:
    emb, _ = embedder()

    assert isinstance(emb, Embedder)
    assert emb.dimension == 1024


def test_model_id_contient_le_nom_et_la_signature() -> None:
    emb, _ = embedder()

    assert emb.model_id == f"{E5}#{get_spec(E5).signature}"


def test_prefixe_passage_e5() -> None:
    emb, factory = embedder()

    emb.embed_passages(["PostgreSQL est relationnel."])

    assert factory.model.calls[0][0] == ["passage: PostgreSQL est relationnel."]


def test_prefixe_requete_e5() -> None:
    emb, factory = embedder()

    emb.embed_query("postgres ou mongo ?")

    assert factory.model.calls[0][0] == ["query: postgres ou mongo ?"]


def test_pas_de_prefixe_pour_potion() -> None:
    emb, factory = embedder(POTION)

    emb.embed_passages(["texte"])
    emb.embed_query("requête")

    assert [call[0] for call in factory.model.calls] == [["texte"], ["requête"]]


def test_vecteurs_normalises() -> None:
    emb, _ = embedder()

    vectors = emb.embed_passages(["abcd", "a"])  # (13, 0, 3) et (10, 0, 3) avec "passage: "
    query = emb.embed_query("x")

    for vector in [*vectors, query]:
        assert math.isclose(math.fsum(v * v for v in vector), 1.0, rel_tol=1e-6)
    assert vectors[0] == pytest.approx([13 / math.sqrt(178), 0.0, 3 / math.sqrt(178)])


def test_vecteur_nul_reste_nul() -> None:
    class ZeroModel(FakeModel):
        def embed(self, documents: Sequence[str], batch_size: int) -> Iterable[NDArray[np.float32]]:
            for _ in documents:
                yield np.zeros(3, dtype=np.float32)

    config = EmbeddingConfig(model_name=POTION, cache_dir=Path("/cache"))
    emb = FastEmbedEmbedder(config, model_factory=lambda name, cache: ZeroModel())

    assert emb.embed_query("") == [0.0, 0.0, 0.0]


def test_ordre_et_types_conserves() -> None:
    emb, _ = embedder(POTION)

    vectors = emb.embed_passages(["aaaa", "a", "aa"])

    assert len(vectors) == 3
    assert all(type(v) is float for vector in vectors for v in vector)
    assert [vector[0] > vector[2] for vector in vectors] == [True, False, False]


def test_taille_de_lot_transmise() -> None:
    emb, factory = embedder(batch_size=7)

    emb.embed_passages(["a", "b"])

    assert factory.model.calls[0][1] == 7


def test_chargement_paresseux_et_unique() -> None:
    emb, factory = embedder()
    assert factory.loads == []

    emb.embed_query("a")
    emb.embed_passages(["b"])

    assert factory.loads == [(E5, Path("/cache/models"))]


def test_liste_vide_ne_charge_pas_le_modele() -> None:
    emb, factory = embedder()

    assert emb.embed_passages([]) == []
    assert factory.loads == []


# --- Configuration ------------------------------------------------------------------------


def test_cache_des_modeles_durable_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    assert default_model_cache_dir() == Path.home() / ".cache/second-brain/models"


def test_cache_des_modeles_respecte_xdg_cache_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert default_model_cache_dir() == tmp_path / "second-brain" / "models"
