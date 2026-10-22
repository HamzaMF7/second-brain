"""La table chunks_fts reste synchronisée avec chunks (triggers de la migration 002)."""

import sqlite3
from pathlib import Path

import pytest

from second_brain.storage.db import connect, open_database
from second_brain.storage.documents import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    delete_documents,
    save_document,
)
from second_brain.storage.migrator import load_migrations, migrate


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_database(tmp_path / "a.db")


def record(path: str) -> DocumentRecord:
    return DocumentRecord(Path(path), 10, 1_000, "h", DocumentStatus.INDEXED)


def matches(conn: sqlite3.Connection, query: str) -> list[str]:
    """Chemins des documents dont un chunk correspond à la requête FTS5."""
    rows = conn.execute(
        "SELECT d.path FROM chunks_fts"
        " JOIN chunks c ON c.id = chunks_fts.rowid"
        " JOIN documents d ON d.id = c.document_id"
        " WHERE chunks_fts MATCH ? ORDER BY d.path",
        (query,),
    ).fetchall()
    return [path for (path,) in rows]


def assert_index_consistent(conn: sqlite3.Connection) -> None:
    """Compare l'index FTS5 au contenu réel de chunks ; lève une erreur s'ils divergent."""
    with conn:
        conn.execute("INSERT INTO chunks_fts (chunks_fts, rank) VALUES ('integrity-check', 1)")


def test_un_chunk_enregistre_est_trouve(conn: sqlite3.Connection) -> None:
    save_document(conn, record("/a.md"), [ChunkRecord(0, "PostgreSQL contre MongoDB")])

    assert matches(conn, "mongodb") == ["/a.md"]
    assert matches(conn, "oracle") == []
    assert_index_consistent(conn)


def test_les_accents_et_la_casse_sont_ignores(conn: sqlite3.Connection) -> None:
    save_document(conn, record("/a.md"), [ChunkRecord(0, "L'élève étudie à Noël")])

    assert matches(conn, "eleve") == ["/a.md"]
    assert matches(conn, "ÉLÈVE") == ["/a.md"]
    assert matches(conn, "noel") == ["/a.md"]


def test_supprimer_un_document_le_retire_de_la_recherche(conn: sqlite3.Connection) -> None:
    kept = save_document(conn, record("/garde.md"), [ChunkRecord(0, "archives municipales")])
    gone = save_document(conn, record("/parti.md"), [ChunkRecord(0, "archives scolaires")])
    assert matches(conn, "archives") == ["/garde.md", "/parti.md"]

    delete_documents(conn, [gone])  # chunks supprimés par ON DELETE CASCADE

    assert matches(conn, "archives") == ["/garde.md"]
    assert matches(conn, "scolaires") == []
    assert kept
    assert_index_consistent(conn)


def test_remplacer_un_document_oublie_ses_anciens_mots(conn: sqlite3.Connection) -> None:
    save_document(conn, record("/a.md"), [ChunkRecord(0, "version ancienne")])

    save_document(conn, record("/a.md"), [ChunkRecord(0, "version nouvelle")])

    assert matches(conn, "ancienne") == []
    assert matches(conn, "nouvelle") == ["/a.md"]
    assert_index_consistent(conn)


def test_modifier_le_texte_d_un_chunk_met_l_index_a_jour(conn: sqlite3.Connection) -> None:
    save_document(conn, record("/a.md"), [ChunkRecord(0, "texte avant")])

    with conn:
        conn.execute("UPDATE chunks SET text = 'texte apres'")

    assert matches(conn, "avant") == []
    assert matches(conn, "apres") == ["/a.md"]
    assert_index_consistent(conn)


def test_la_migration_indexe_les_chunks_deja_presents(tmp_path: Path) -> None:
    # Base créée avant l'existence de chunks_fts : seule la migration 001 est appliquée.
    conn = connect(tmp_path / "a.db")
    initial = [m for m in load_migrations() if m.version == 1]
    migrate(conn, initial)
    # SQL brut : le code actuel (save_document) écrit des colonnes que la v1 n'a pas.
    with conn:
        conn.execute(
            "INSERT INTO documents (path, filename, extension, size, mtime, content_hash,"
            " status, indexed_at) VALUES ('/ancien.md', 'ancien.md', '.md', 1, 1, 'h',"
            " 'indexed', 'x')"
        )
        conn.execute(
            "INSERT INTO chunks (document_id, chunk_index, text)"
            " VALUES (1, 0, 'document indexé avant FTS')"
        )

    migrate(conn)  # applique 002 et les suivantes

    assert matches(conn, "fts") == ["/ancien.md"]
    assert_index_consistent(conn)


def test_l_index_ne_stocke_pas_une_copie_du_texte(conn: sqlite3.Connection) -> None:
    # external content : pas de table chunks_fts_content.
    names = {name for (name,) in conn.execute("SELECT name FROM sqlite_master")}

    assert "chunks_fts" in names
    assert "chunks_fts_content" not in names
