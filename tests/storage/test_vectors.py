import sqlite3
from pathlib import Path

import pytest

from second_brain.storage import db
from second_brain.storage.db import VectorExtensionError, connect, open_database
from second_brain.storage.documents import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    delete_documents,
    save_document,
)
from second_brain.storage.vectors import deserialize, get_vector, save_vectors, serialize


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_database(tmp_path / "a.db")


def add_document(conn: sqlite3.Connection, *texts: str) -> tuple[int, list[int]]:
    record = DocumentRecord(
        path=Path("/notes/a.md"),
        size=10,
        mtime_ns=1_000,
        content_hash="h1",
        status=DocumentStatus.INDEXED,
        error=None,
    )
    document_id = save_document(
        conn, record, [ChunkRecord(i, text) for i, text in enumerate(texts)]
    )
    rows = conn.execute(
        "SELECT id FROM chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)
    ).fetchall()
    return document_id, [chunk_id for (chunk_id,) in rows]


def vector_count(conn: sqlite3.Connection) -> int:
    (count,) = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()
    return int(count)


# --- Sérialisation ------------------------------------------------------------------------


def test_serialisation_float32_little_endian() -> None:
    assert serialize([1.0, -2.0]) == bytes.fromhex("0000803f000000c0")


def test_aller_retour_exact_pour_les_valeurs_representables() -> None:
    assert deserialize(serialize([0.5, -0.25, 1.0, 0.0])) == [0.5, -0.25, 1.0, 0.0]


def test_aller_retour_arrondi_en_float32() -> None:
    assert deserialize(serialize([0.1])) == pytest.approx([0.1], rel=1e-7)


# --- Table chunk_vectors ------------------------------------------------------------------


def test_save_puis_get_vector(conn: sqlite3.Connection) -> None:
    _, (chunk_id,) = add_document(conn, "un")

    save_vectors(conn, "modele#abc", [(chunk_id, [0.6, 0.8])])

    assert get_vector(conn, chunk_id) == ("modele#abc", pytest.approx([0.6, 0.8]))


def test_get_vector_absent(conn: sqlite3.Connection) -> None:
    _, (chunk_id,) = add_document(conn, "un")

    assert get_vector(conn, chunk_id) is None


def test_save_remplace_le_vecteur_et_le_modele(conn: sqlite3.Connection) -> None:
    _, (chunk_id,) = add_document(conn, "un")

    save_vectors(conn, "ancien#1", [(chunk_id, [1.0, 0.0])])
    save_vectors(conn, "nouveau#2", [(chunk_id, [0.0, 1.0])])

    assert get_vector(conn, chunk_id) == ("nouveau#2", [0.0, 1.0])
    assert vector_count(conn) == 1


def test_supprimer_le_document_purge_ses_vecteurs(conn: sqlite3.Connection) -> None:
    document_id, chunk_ids = add_document(conn, "un", "deux")
    save_vectors(conn, "m#1", [(chunk_id, [1.0, 0.0]) for chunk_id in chunk_ids])

    delete_documents(conn, [document_id])

    assert vector_count(conn) == 0


def test_redecouper_le_document_purge_ses_vecteurs(conn: sqlite3.Connection) -> None:
    _, chunk_ids = add_document(conn, "un", "deux")
    save_vectors(conn, "m#1", [(chunk_id, [1.0, 0.0]) for chunk_id in chunk_ids])

    add_document(conn, "un, modifié")  # save_document remplace les chunks

    assert vector_count(conn) == 0


def test_vecteur_sans_chunk_refuse(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        save_vectors(conn, "m#1", [(9999, [1.0])])


def test_vecteur_vide_refuse(conn: sqlite3.Connection) -> None:
    _, (chunk_id,) = add_document(conn, "un")

    with pytest.raises(sqlite3.IntegrityError):
        save_vectors(conn, "m#1", [(chunk_id, [])])


# --- Extension sqlite-vec -----------------------------------------------------------------


def test_fonctions_vec_disponibles_apres_connect(tmp_path: Path) -> None:
    conn = connect(tmp_path / "a.db")

    (distance,) = conn.execute(
        "SELECT vec_distance_cosine(?, ?)", (serialize([1.0, 0.0]), serialize([0.6, 0.8]))
    ).fetchone()

    assert distance == pytest.approx(0.4)  # 1 − cos, avec cos = 0,6


def test_extension_introuvable_erreur_explicite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "_extension_path", lambda: str(tmp_path / "absente"))

    with pytest.raises(VectorExtensionError, match="sqlite-vec"):
        connect(tmp_path / "a.db")
