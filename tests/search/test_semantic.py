"""Recherche sémantique : vecteurs posés à la main pour que les scores se calculent de tête."""

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest
from fakes import FakeEmbedder

from second_brain.config import SearchConfig
from second_brain.search.base import Retriever
from second_brain.search.grouping import search_documents
from second_brain.search.semantic import SemanticRetriever
from second_brain.storage.db import open_database
from second_brain.storage.documents import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    save_document,
)
from second_brain.storage.vectors import save_vectors

MODEL = "faux#1"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_database(tmp_path / "a.db")


def add(
    conn: sqlite3.Connection,
    path: str,
    chunks: Sequence[tuple[str, list[float]]],
    model_id: str = MODEL,
) -> None:
    """Un document, ses chunks et leurs vecteurs."""
    record = DocumentRecord(Path(path), 10, 1_000, "h", DocumentStatus.INDEXED)
    document_id = save_document(
        conn, record, [ChunkRecord(i, text) for i, (text, _) in enumerate(chunks)]
    )
    ids = [
        chunk_id
        for (chunk_id,) in conn.execute(
            "SELECT id FROM chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)
        )
    ]
    save_vectors(conn, model_id, [(i, vector) for i, (_, vector) in zip(ids, chunks, strict=True)])


def retriever(conn: sqlite3.Connection, query_vector: list[float]) -> SemanticRetriever:
    return SemanticRetriever(conn, FakeEmbedder(MODEL, query_vector=query_vector))


def test_respecte_le_contrat() -> None:
    assert issubclass(SemanticRetriever, Retriever)


def test_classe_par_cosinus_et_score_est_le_cosinus(conn: sqlite3.Connection) -> None:
    add(conn, "/n/loin.md", [("loin", [0.0, 1.0])])
    add(conn, "/n/proche.md", [("proche", [1.0, 0.0])])
    add(conn, "/n/moyen.md", [("moyen", [0.6, 0.8])])

    results = retriever(conn, [1.0, 0.0]).search("requête", 10)

    assert [r.path.name for r in results] == ["proche.md", "moyen.md", "loin.md"]
    assert [r.score for r in results] == pytest.approx([1.0, 0.6, 0.0], abs=1e-6)


def test_score_negatif_pour_un_sens_oppose(conn: sqlite3.Connection) -> None:
    add(conn, "/n/oppose.md", [("oppose", [-1.0, 0.0])])

    (result,) = retriever(conn, [1.0, 0.0]).search("requête", 10)

    assert result.score == pytest.approx(-1.0)


def test_k_limite_les_resultats(conn: sqlite3.Connection) -> None:
    for i in range(5):
        add(conn, f"/n/{i}.md", [(f"t{i}", [1.0, float(i)])])

    assert len(retriever(conn, [1.0, 0.0]).search("requête", 3)) == 3


@pytest.mark.parametrize(("query", "k"), [("requête", 0), ("requête", -1), ("   ", 5)])
def test_requete_vide_ou_k_nul(conn: sqlite3.Connection, query: str, k: int) -> None:
    add(conn, "/n/a.md", [("texte", [1.0, 0.0])])
    embedder = FakeEmbedder(MODEL, query_vector=[1.0, 0.0])

    assert SemanticRetriever(conn, embedder).search(query, k) == []
    assert embedder.queries == []  # modèle pas sollicité


def test_ignore_les_vecteurs_d_un_autre_modele(conn: sqlite3.Connection) -> None:
    add(conn, "/n/courant.md", [("courant", [0.6, 0.8])])
    add(conn, "/n/ancien.md", [("ancien", [1.0, 0.0])], model_id="ancien#0")

    results = retriever(conn, [1.0, 0.0]).search("requête", 10)

    assert [r.path.name for r in results] == ["courant.md"]


def test_la_requete_passe_par_embed_query(conn: sqlite3.Connection) -> None:
    add(conn, "/n/a.md", [("texte", [1.0, 0.0])])
    embedder = FakeEmbedder(MODEL, query_vector=[1.0, 0.0])

    SemanticRetriever(conn, embedder).search("choix de base", 5)

    assert embedder.queries == ["choix de base"]
    assert embedder.batches == []  # jamais embed_passages pour une requête


def test_extrait_premiers_mots_sans_surlignage(conn: sqlite3.Connection) -> None:
    words = [f"mot{i}" for i in range(30)]
    add(conn, "/n/long.md", [("  ".join(words), [1.0, 0.0])])
    add(conn, "/n/court.md", [("deux\nmots", [1.0, 0.0])])
    config = SearchConfig(snippet_tokens=24)
    retriever = SemanticRetriever(conn, FakeEmbedder(MODEL, query_vector=[1.0, 0.0]), config)

    snippets = {r.path.name: r.snippet for r in retriever.search("requête", 10)}

    assert snippets["long.md"] == " ".join(words[:24]) + config.ellipsis
    assert snippets["court.md"] == "deux mots"
    assert config.highlight_open not in snippets["long.md"]


def test_page_et_section_transmises(conn: sqlite3.Connection) -> None:
    record = DocumentRecord(Path("/n/doc.pdf"), 10, 1_000, "h", DocumentStatus.INDEXED)
    save_document(conn, record, [ChunkRecord(0, "texte", page=3, section="Intro")])
    (chunk_id,) = conn.execute("SELECT id FROM chunks").fetchone()
    save_vectors(conn, MODEL, [(chunk_id, [1.0, 0.0])])

    (result,) = retriever(conn, [1.0, 0.0]).search("requête", 1)

    assert (result.page, result.section) == (3, "Intro")


def test_regroupement_par_document(conn: sqlite3.Connection) -> None:
    add(conn, "/n/long.md", [(f"partie {i}", [1.0, 0.1 * i]) for i in range(5)])
    add(conn, "/n/autre.md", [("autre", [0.0, 1.0])])

    results = search_documents(retriever(conn, [1.0, 0.0]), "requête", 2, fetch_factor=1)

    assert [r.path.name for r in results] == ["long.md", "autre.md"]
    assert results[0].snippet == "partie 0"
