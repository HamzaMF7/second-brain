"""Accès aux tables documents, chunks et folders (SQL brut, ADR 0008).

Toutes les valeurs passent par des paramètres liés (`?`), jamais par du formatage de chaîne.
"""

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class DocumentStatus(StrEnum):
    INDEXED = "indexed"
    SCANNED = "scanned"  # PDF sans couche de texte : enregistré, sans chunk
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """Ce que la base sait d'un document, pour la détection des changements."""

    id: int
    path: Path
    size: int
    mtime_ns: int
    content_hash: str | None
    status: DocumentStatus
    chunker_id: str | None = None  # NULL : indexé avant la migration 004


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """Document à enregistrer. `error` ne contient jamais de contenu de document."""

    path: Path
    size: int
    mtime_ns: int
    content_hash: str | None
    status: DocumentStatus
    error: str | None = None
    chunker_id: str | None = None  # signature du découpage utilisé


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_index: int
    text: str
    page: int | None = None
    section: str | None = None
    token_count: int | None = None
    context: str | None = None  # préfixe indexé « titre > section », jamais affiché


def documents_under(conn: sqlite3.Connection, root: Path) -> list[StoredDocument]:
    """Documents dont le chemin est dans `root`, triés par chemin.

    Le filtre est fait en Python avec Path.is_relative_to plutôt qu'avec LIKE : un
    `LIKE '/notes%'` prendrait aussi `/notes-old/`, et `_` ou `%` dans un nom de dossier
    seraient interprétés comme des jokers.
    """
    rows = conn.execute(
        "SELECT id, path, size, mtime, content_hash, status, chunker_id"
        " FROM documents ORDER BY path"
    ).fetchall()
    return [
        StoredDocument(
            id, Path(path), size, mtime, content_hash, DocumentStatus(status), chunker_id
        )
        for id, path, size, mtime, content_hash, status, chunker_id in rows
        if Path(path).is_relative_to(root)
    ]


def save_document(
    conn: sqlite3.Connection, record: DocumentRecord, chunks: Sequence[ChunkRecord]
) -> int:
    """Insère ou remplace un document et tous ses chunks, en une seule transaction.

    ON CONFLICT ... DO UPDATE garde l'id du document (contrairement à INSERT OR REPLACE,
    qui supprimerait la ligne puis en créerait une nouvelle avec un autre id).
    """
    with conn:
        (document_id,) = conn.execute(
            """
            INSERT INTO documents
                (path, filename, extension, size, mtime, content_hash, status, error,
                 indexed_at, chunker_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (path) DO UPDATE SET
                size = excluded.size,
                mtime = excluded.mtime,
                content_hash = excluded.content_hash,
                status = excluded.status,
                error = excluded.error,
                indexed_at = excluded.indexed_at,
                chunker_id = excluded.chunker_id
            RETURNING id
            """,
            (
                str(record.path),
                record.path.name,
                record.path.suffix.lower(),
                record.size,
                record.mtime_ns,
                record.content_hash,
                record.status.value,
                record.error,
                _now(),
                record.chunker_id,
            ),
        ).fetchone()
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.executemany(
            "INSERT INTO chunks"
            " (document_id, chunk_index, text, page, section, token_count, context)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (document_id, c.chunk_index, c.text, c.page, c.section, c.token_count, c.context)
                for c in chunks
            ],
        )
    return int(document_id)


def update_file_metadata(
    conn: sqlite3.Connection, document_id: int, size: int, mtime_ns: int
) -> None:
    """Fichier modifié sur le disque mais contenu identique : seules les métadonnées changent."""
    with conn:
        conn.execute(
            "UPDATE documents SET size = ?, mtime = ? WHERE id = ?", (size, mtime_ns, document_id)
        )


def delete_documents(conn: sqlite3.Connection, document_ids: Iterable[int]) -> int:
    """Supprime les documents ; leurs chunks partent avec (ON DELETE CASCADE)."""
    with conn:
        cursor = conn.executemany(
            "DELETE FROM documents WHERE id = ?", [(document_id,) for document_id in document_ids]
        )
    return cursor.rowcount


def ensure_folder(conn: sqlite3.Connection, root: Path) -> None:
    """Enregistre un dossier indexé (sans effet s'il est déjà connu)."""
    with conn:
        conn.execute(
            "INSERT INTO folders (path) VALUES (?) ON CONFLICT (path) DO NOTHING", (str(root),)
        )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
