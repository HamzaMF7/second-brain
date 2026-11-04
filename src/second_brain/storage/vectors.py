"""Accès à la table chunk_vectors : un vecteur par chunk, avec son model_id."""

import sqlite3
import struct
from collections.abc import Sequence


def serialize(vector: Sequence[float]) -> bytes:
    """float32 little-endian, le format des BLOB lus par sqlite-vec."""
    return struct.pack(f"<{len(vector)}f", *vector)


def deserialize(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def save_vectors(
    conn: sqlite3.Connection, model_id: str, items: Sequence[tuple[int, Sequence[float]]]
) -> None:
    """Enregistre (chunk_id, vecteur) en une transaction ; remplace un vecteur existant."""
    with conn:
        conn.executemany(
            """
            INSERT INTO chunk_vectors (chunk_id, model_id, embedding) VALUES (?, ?, ?)
            ON CONFLICT (chunk_id) DO UPDATE SET
                model_id = excluded.model_id,
                embedding = excluded.embedding
            """,
            [(chunk_id, model_id, serialize(vector)) for chunk_id, vector in items],
        )


def chunks_needing_vectors(conn: sqlite3.Connection, model_id: str) -> list[int]:
    """Identifiants des chunks sans vecteur, ou dont le vecteur vient d'un autre modèle.

    Toute la base, pas seulement un dossier : un changement de modèle vaut partout.
    """
    rows = conn.execute(
        """
        SELECT c.id FROM chunks c
        LEFT JOIN chunk_vectors v ON v.chunk_id = c.id
        WHERE v.chunk_id IS NULL OR v.model_id != ?
        ORDER BY c.id
        """,
        (model_id,),
    ).fetchall()
    return [chunk_id for (chunk_id,) in rows]


def chunk_texts(
    conn: sqlite3.Connection, chunk_ids: Sequence[int]
) -> list[tuple[int, str, str | None]]:
    """(id, texte, contexte) des chunks demandés, dans l'ordre de `chunk_ids`."""
    placeholders = ", ".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT id, text, context FROM chunks WHERE id IN ({placeholders})", list(chunk_ids)
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


def get_vector(conn: sqlite3.Connection, chunk_id: int) -> tuple[str, list[float]] | None:
    """(model_id, vecteur) du chunk, ou None s'il n'a pas encore de vecteur."""
    row = conn.execute(
        "SELECT model_id, embedding FROM chunk_vectors WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    if row is None:
        return None
    model_id, blob = row
    return str(model_id), deserialize(blob)
