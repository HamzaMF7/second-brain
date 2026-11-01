"""Pipeline d'indexation : scan → changements → extraction → base, puis vecteurs.

Phase 1 (texte) : un document = une transaction. Une erreur sur un fichier lui donne le
statut `error` et le pipeline continue.
Phase 2 (vecteurs) : index dérivé, calculé par lots pour tous les chunks sans vecteur ou
d'un autre modèle. Un vecteur n'est jamais périmé (supprimé avec son chunk), seulement
manquant : une interruption est reprise au passage suivant.
Les logs ne contiennent que document_id, nom, statut, compteurs et durées.
"""

import logging
import sqlite3
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from second_brain.chunking.base import Chunker
from second_brain.chunking.structured import StructuredChunker
from second_brain.config import EmbeddingConfig, ScanConfig
from second_brain.embeddings.base import Embedder
from second_brain.extraction.errors import ExtractionError
from second_brain.extraction.registry import ExtractorRegistry
from second_brain.indexing.changes import KnownDocument, detect_changes, sha256_file
from second_brain.indexing.scanner import ScannedFile, SkipReason, scan
from second_brain.storage.documents import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    delete_documents,
    documents_under,
    ensure_folder,
    save_document,
    update_file_metadata,
)
from second_brain.storage.vectors import chunk_texts, chunks_needing_vectors, save_vectors

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]  # (éléments traités, total à traiter)


class EmbeddingError(Exception):
    """Le modèle d'embeddings a échoué : le texte est indexé, les vecteurs sont incomplets."""


@dataclass(slots=True)
class IndexReport:
    added: int = 0
    modified: int = 0
    touched: int = 0  # mtime changé, contenu identique
    unchanged: int = 0
    deleted: int = 0
    scanned_pdfs: int = 0  # comptés aussi dans added ou modified
    errors: int = 0
    skipped: Counter[SkipReason] = field(default_factory=Counter)
    embedded: int = 0  # vecteurs calculés (nouveaux chunks ou changement de modèle)
    embedding_seconds: float = 0.0
    seconds: float = 0.0


def index_folder(
    conn: sqlite3.Connection,
    root: Path,
    registry: ExtractorRegistry,
    *,
    chunker: Chunker | None = None,
    scan_config: ScanConfig | None = None,
    hash_file: Callable[[Path], str] = sha256_file,
    on_progress: ProgressCallback | None = None,
    embedder: Embedder | None = None,
    embedding_config: EmbeddingConfig | None = None,
    on_embed_progress: ProgressCallback | None = None,
) -> IndexReport:
    """Met la base à jour pour le dossier `root` et renvoie un résumé.

    Sans `embedder`, la phase 2 (vecteurs) est sautée.
    """
    start = time.perf_counter()
    chunker = chunker or StructuredChunker()
    root = root.resolve()
    scanned = scan(root, registry.supports, scan_config)
    known = [
        KnownDocument(
            id=d.id,
            path=d.path,
            size=d.size,
            mtime_ns=d.mtime_ns,
            content_hash=d.content_hash,
            had_error=d.status is DocumentStatus.ERROR,
            chunker_id=d.chunker_id,
        )
        for d in documents_under(conn, root)
    ]
    changes = detect_changes(scanned.files, known, hash_file, chunker_id=chunker.id)
    report = IndexReport(unchanged=len(changes.unchanged), skipped=scanned.skipped)

    ensure_folder(conn, root)
    if changes.deleted:
        report.deleted = delete_documents(conn, [d.id for d in changes.deleted])
    for change in changes.touched:
        update_file_metadata(conn, change.document_id, change.file.size, change.file.mtime_ns)
    report.touched = len(changes.touched)

    todo: list[tuple[ScannedFile, str | None, bool]] = [(f, None, True) for f in changes.new]
    todo += [(c.file, c.content_hash, False) for c in changes.modified]
    for done, (file, content_hash, is_new) in enumerate(todo, start=1):
        status = _index_file(conn, registry, chunker, file, content_hash, hash_file)
        if status is DocumentStatus.ERROR:
            report.errors += 1
        elif is_new:
            report.added += 1
        else:
            report.modified += 1
        if status is DocumentStatus.SCANNED:
            report.scanned_pdfs += 1
        if on_progress is not None:
            on_progress(done, len(todo))

    if embedder is not None:
        embed_start = time.perf_counter()
        batch_size = (embedding_config or EmbeddingConfig()).batch_size
        report.embedded = _embed_pending(conn, embedder, batch_size, on_embed_progress)
        report.embedding_seconds = time.perf_counter() - embed_start
        logger.info(
            "vecteurs=%d modèle=%s durée=%.1f s",
            report.embedded,
            embedder.model_id,
            report.embedding_seconds,
        )

    report.seconds = time.perf_counter() - start
    return report


def _embed_pending(
    conn: sqlite3.Connection,
    embedder: Embedder,
    batch_size: int,
    on_progress: ProgressCallback | None,
) -> int:
    """Calcule et enregistre, lot par lot, les vecteurs manquants ; renvoie leur nombre.

    Chaque lot est enregistré dès qu'il est calculé : après une erreur, les lots finis
    sont gardés et le passage suivant ne traite que le reste.
    """
    pending = chunks_needing_vectors(conn, embedder.model_id)
    for start in range(0, len(pending), batch_size):
        rows = chunk_texts(conn, pending[start : start + batch_size])
        texts = [f"{context}\n\n{text}" if context else text for _, text, context in rows]
        try:
            vectors = embedder.embed_passages(texts)
        except Exception as exc:  # message du modèle inconnu : jamais recopié (contenu ?)
            raise EmbeddingError(
                f"échec du modèle {embedder.model_id} ({type(exc).__name__})"
            ) from None
        ids = [chunk_id for chunk_id, _, _ in rows]
        save_vectors(conn, embedder.model_id, list(zip(ids, vectors, strict=True)))
        if on_progress is not None:
            on_progress(min(start + batch_size, len(pending)), len(pending))
    return len(pending)


def _index_file(
    conn: sqlite3.Connection,
    registry: ExtractorRegistry,
    chunker: Chunker,
    file: ScannedFile,
    content_hash: str | None,
    hash_file: Callable[[Path], str],
) -> DocumentStatus:
    """Extrait un fichier et l'enregistre (avec ses chunks) en une transaction."""
    start = time.perf_counter()
    status = DocumentStatus.ERROR
    error: str | None = None
    chunks: list[ChunkRecord] = []
    try:
        if content_hash is None:
            content_hash = hash_file(file.path)
        doc = registry.for_path(file.path).extract(file.path)
    except OSError:
        error = f"Lecture impossible : {file.path.name}"
    except ExtractionError as exc:  # nos messages ne contiennent jamais de contenu
        error = f"{type(exc).__name__} : {exc}"
    except Exception as exc:  # bug : message inconnu, donc jamais enregistré
        error = f"{type(exc).__name__} (erreur inattendue) : {file.path.name}"
    else:
        status = DocumentStatus.SCANNED if doc.is_scanned else DocumentStatus.INDEXED
        if status is DocumentStatus.INDEXED:
            chunks = [
                ChunkRecord(
                    chunk_index=c.index,
                    text=c.text,
                    page=c.page,
                    section=c.section,
                    token_count=c.token_count,
                    context=c.context,
                )
                for c in chunker.chunk(doc)
            ]

    record = DocumentRecord(
        file.path, file.size, file.mtime_ns, content_hash, status, error, chunker.id
    )
    document_id = save_document(conn, record, chunks)
    logger.info(
        "document_id=%d fichier=%s statut=%s durée=%.0f ms%s",
        document_id,
        file.path.name,
        status.value,
        (time.perf_counter() - start) * 1000,
        f" erreur={error}" if error else "",
    )
    return status
