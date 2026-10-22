"""Colonne chunks.context : indexée par FTS5, jamais affichée dans les extraits."""

import sqlite3
from pathlib import Path

import pytest

from second_brain.search.lexical import LexicalRetriever
from second_brain.storage.db import connect, open_database
from second_brain.storage.documents import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    save_document,
)
from second_brain.storage.migrator import load_migrations, migrate

FILLER = ["recette de cuisine", "horaires de natation", "liste de courses", "roman policier"]


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    conn = open_database(tmp_path / "a.db")
    for i, text in enumerate(FILLER):
        add(conn, f"/divers-{i}.md", text)
    return conn


def add(conn: sqlite3.Connection, path: str, text: str, context: str | None = None) -> int:
    record = DocumentRecord(Path(path), 10, 1_000, "h", DocumentStatus.INDEXED)
    return save_document(conn, record, [ChunkRecord(0, text, context=context)])


def check_index(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("INSERT INTO chunks_fts (chunks_fts, rank) VALUES ('integrity-check', 1)")


def test_un_mot_present_seulement_dans_le_contexte_trouve_le_chunk(
    conn: sqlite3.Connection,
) -> None:
    add(conn, "/rapport.pdf", "Le taux a baissé cette année.", context="Rapport annuel > Synthèse")

    (result,) = LexicalRetriever(conn).search("synthèse", 5)

    assert result.path == Path("/rapport.pdf")
    check_index(conn)


def test_l_extrait_affiche_le_texte_d_origine_sans_le_contexte(conn: sqlite3.Connection) -> None:
    add(conn, "/rapport.pdf", "Le taux a baissé cette année.", context="Rapport annuel > Synthèse")

    (result,) = LexicalRetriever(conn).search("taux synthèse", 5)

    assert "taux" in result.snippet
    assert "Synthèse" not in result.snippet
    assert "Rapport annuel" not in result.snippet


def test_contexte_absent_accepte(conn: sqlite3.Connection) -> None:
    add(conn, "/a.md", "texte sans contexte")

    assert [r.path for r in LexicalRetriever(conn).search("contexte", 5)] == [Path("/a.md")]
    check_index(conn)


def test_remplacer_un_document_oublie_son_ancien_contexte(conn: sqlite3.Connection) -> None:
    add(conn, "/a.md", "texte", context="Ancien titre")
    add(conn, "/a.md", "texte", context="Nouveau titre")

    assert LexicalRetriever(conn).search("ancien", 5) == []
    assert len(LexicalRetriever(conn).search("nouveau", 5)) == 1
    check_index(conn)


def test_la_migration_conserve_les_chunks_existants(tmp_path: Path) -> None:
    # Base créée avant la colonne context : migrations 001 et 002 seulement.
    conn = connect(tmp_path / "a.db")
    migrate(conn, [m for m in load_migrations() if m.version <= 2])
    with conn:
        conn.execute(
            "INSERT INTO documents (path, filename, extension, size, mtime, content_hash,"
            " status, indexed_at) VALUES ('/a.md', 'a.md', '.md', 1, 1, 'h', 'indexed', 'x')"
        )
        conn.execute(
            "INSERT INTO chunks (document_id, chunk_index, text) VALUES (1, 0, 'archives')"
        )

    migrate(conn)

    assert conn.execute("SELECT context FROM chunks").fetchone() == (None,)
    assert [r.path for r in LexicalRetriever(conn).search("archives", 5)] == [Path("/a.md")]
    check_index(conn)
