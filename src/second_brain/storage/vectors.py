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


def get_vector(conn: sqlite3.Connection, chunk_id: int) -> tuple[str, list[float]] | None:
    """(model_id, vecteur) du chunk, ou None s'il n'a pas encore de vecteur."""
    row = conn.execute(
        "SELECT model_id, embedding FROM chunk_vectors WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    if row is None:
        return None
    model_id, blob = row
    return str(model_id), deserialize(blob)
