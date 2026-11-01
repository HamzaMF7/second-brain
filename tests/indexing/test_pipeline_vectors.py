"""Phase 2 du pipeline : calcul des vecteurs des chunks qui n'en ont pas (ou d'un autre modèle)."""

import sqlite3
from pathlib import Path

import pytest
from fakes import FakeEmbedder

from second_brain.chunking.structured import StructuredChunker
from second_brain.config import ChunkingConfig, EmbeddingConfig
from second_brain.extraction.registry import default_registry
from second_brain.indexing.pipeline import EmbeddingError, IndexReport, index_folder
from second_brain.storage.db import open_database


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_database(tmp_path / "index.db")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "notes"
    folder.mkdir()
    return folder


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def run(
    conn: sqlite3.Connection,
    root: Path,
    embedder: FakeEmbedder | None,
    batch_size: int = 32,
    chunker: StructuredChunker | None = None,
) -> IndexReport:
    return index_folder(
        conn,
        root,
        default_registry(),
        chunker=chunker,
        embedder=embedder,
        embedding_config=EmbeddingConfig(batch_size=batch_size),
    )


def vectors(conn: sqlite3.Connection) -> dict[int, str]:
    """chunk_id → model_id."""
    return dict(conn.execute("SELECT chunk_id, model_id FROM chunk_vectors").fetchall())


def chunk_ids(conn: sqlite3.Connection) -> set[int]:
    return {chunk_id for (chunk_id,) in conn.execute("SELECT id FROM chunks")}


def test_chaque_chunk_recoit_un_vecteur(conn: sqlite3.Connection, root: Path) -> None:
    write(root / "a.md", "Premier texte.")
    write(root / "b.txt", "Second texte.")
    embedder = FakeEmbedder("modele#1")

    report = run(conn, root, embedder)

    assert set(vectors(conn)) == chunk_ids(conn)
    assert set(vectors(conn).values()) == {"modele#1"}
    assert report.embedded == 2
    assert sorted(embedder.embedded_texts) == ["Premier texte.", "Second texte."]


def test_second_passage_n_appelle_pas_le_modele(conn: sqlite3.Connection, root: Path) -> None:
    write(root / "a.md", "Texte.")
    run(conn, root, FakeEmbedder())
    embedder = FakeEmbedder()

    report = run(conn, root, embedder)

    assert embedder.batches == []
    assert report.embedded == 0


def test_changer_de_modele_recalcule_tous_les_vecteurs(
    conn: sqlite3.Connection, root: Path
) -> None:
    write(root / "a.md", "Un.")
    write(root / "b.md", "Deux.")
    run(conn, root, FakeEmbedder("ancien#1"))

    report = run(conn, root, FakeEmbedder("nouveau#2"))

    assert report.unchanged == 2  # le texte n'est pas retraité
    assert report.embedded == 2
    assert set(vectors(conn).values()) == {"nouveau#2"}


def test_seuls_les_chunks_du_fichier_modifie_sont_recalcules(
    conn: sqlite3.Connection, root: Path
) -> None:
    write(root / "a.md", "Inchangé.")
    path = write(root / "b.md", "Avant.")
    run(conn, root, FakeEmbedder())
    embedder = FakeEmbedder()

    write(path, "Après, plus long.")
    run(conn, root, embedder)

    assert embedder.embedded_texts == ["Après, plus long."]
    assert set(vectors(conn)) == chunk_ids(conn)


def test_document_en_erreur_sans_vecteur(conn: sqlite3.Connection, root: Path) -> None:
    (root / "corrompu.pdf").write_bytes(b"pas un PDF")
    embedder = FakeEmbedder()

    report = run(conn, root, embedder)

    assert report.errors == 1
    assert embedder.batches == []
    assert vectors(conn) == {}


def test_lots_de_la_taille_configuree_et_progression(conn: sqlite3.Connection, root: Path) -> None:
    for i in range(5):
        write(root / f"{i}.md", f"Texte {i}.")
    embedder = FakeEmbedder()
    calls: list[tuple[int, int]] = []

    index_folder(
        conn,
        root,
        default_registry(),
        embedder=embedder,
        embedding_config=EmbeddingConfig(batch_size=2),
        on_embed_progress=lambda done, total: calls.append((done, total)),
    )

    assert [len(batch) for batch in embedder.batches] == [2, 2, 1]
    assert calls == [(2, 5), (4, 5), (5, 5)]


def test_le_contexte_precede_le_texte(conn: sqlite3.Connection, root: Path) -> None:
    write(root / "a.md", "# Titre\n\nCorps du texte.")
    chunker = StructuredChunker(ChunkingConfig(context_prefix=True))
    embedder = FakeEmbedder()

    run(conn, root, embedder, chunker=chunker)

    (text,) = embedder.embedded_texts
    assert text.endswith("\n\nCorps du texte.")
    assert "Titre" in text.removesuffix("Corps du texte.")


def test_modele_en_panne_garde_le_texte_et_les_lots_finis(
    conn: sqlite3.Connection, root: Path
) -> None:
    for i in range(3):
        write(root / f"{i}.md", f"Texte {i}.")

    with pytest.raises(EmbeddingError, match="RuntimeError") as error:
        run(conn, root, FakeEmbedder(fail_on_call=2), batch_size=2)

    assert "modèle en panne" not in str(error.value)  # message du modèle jamais recopié
    assert len(chunk_ids(conn)) == 3  # phase 1 terminée
    assert len(vectors(conn)) == 2  # premier lot enregistré

    embedder = FakeEmbedder()
    report = run(conn, root, embedder, batch_size=2)

    assert report.embedded == 1  # reprise : seul le chunk manquant
    assert set(vectors(conn)) == chunk_ids(conn)


def test_sans_embedder_aucun_vecteur(conn: sqlite3.Connection, root: Path) -> None:
    write(root / "a.md", "Texte.")

    report = run(conn, root, None)

    assert len(chunk_ids(conn)) == 1
    assert vectors(conn) == {}
    assert report.embedded == 0


def test_rapport_mesure_la_duree_des_embeddings(conn: sqlite3.Connection, root: Path) -> None:
    write(root / "a.md", "Texte.")

    report = run(conn, root, FakeEmbedder())

    assert 0 < report.embedding_seconds <= report.seconds
