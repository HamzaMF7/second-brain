"""Détection des changements entre le disque (scanner) et la base (documents connus).

Module pur : il ne lit ni n'écrit la base. Entonnoir du moins cher au plus cher :
taille + mtime (métadonnées), puis hash du contenu seulement si nécessaire.
"""

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from second_brain.indexing.scanner import ScannedFile

_HASH_BLOCK_SIZE = 1024 * 1024  # lecture par blocs : mémoire constante, même pour 50 Mo


@dataclass(frozen=True, slots=True)
class KnownDocument:
    """Ce que la base sait d'un document indexé."""

    id: int
    path: Path
    size: int
    mtime_ns: int
    content_hash: str | None
    had_error: bool  # statut `error` au dernier passage
    chunker_id: str | None = None  # signature du découpage utilisé (None : inconnue)


@dataclass(frozen=True, slots=True)
class KnownChange:
    """Un document déjà en base dont le fichier a bougé sur le disque."""

    file: ScannedFile
    document_id: int
    content_hash: str | None  # None : pas calculé (inutile) ou fichier illisible


@dataclass(slots=True)
class ChangeSet:
    new: list[ScannedFile] = field(default_factory=list)
    modified: list[KnownChange] = field(default_factory=list)  # à réindexer
    touched: list[KnownChange] = field(default_factory=list)  # contenu identique : métadonnées
    unchanged: list[KnownDocument] = field(default_factory=list)
    deleted: list[KnownDocument] = field(default_factory=list)


def detect_changes(
    scanned: Iterable[ScannedFile],
    known: Iterable[KnownDocument],
    hash_file: Callable[[Path], str],
    chunker_id: str | None = None,
) -> ChangeSet:
    """Classe chaque fichier et chaque document connu dans exactement une catégorie.

    Si `chunker_id` est donné, un document découpé avec d'autres réglages est à refaire,
    même si son fichier n'a pas changé.
    """
    remaining = {document.path: document for document in known}
    changes = ChangeSet()

    for file in scanned:
        document = remaining.pop(file.path, None)
        if document is None:
            changes.new.append(file)
        elif document.had_error:
            # Retenté à chaque passage : ex. droits rétablis par chmod, sans changer le mtime.
            changes.modified.append(KnownChange(file, document.id, None))
        elif chunker_id is not None and document.chunker_id != chunker_id:
            # Découpage différent : à redécouper, inutile de lire le fichier pour le savoir.
            changes.modified.append(KnownChange(file, document.id, None))
        elif file.size == document.size and file.mtime_ns == document.mtime_ns:
            changes.unchanged.append(document)
        elif file.size != document.size:
            # Tailles différentes = contenus différents : inutile de lire le fichier.
            changes.modified.append(KnownChange(file, document.id, None))
        else:
            _compare_hashes(file, document, hash_file, changes)

    # Tout document connu qui n'a pas été retrouvé sur le disque a disparu.
    changes.deleted.extend(remaining.values())
    return changes


def _compare_hashes(
    file: ScannedFile,
    document: KnownDocument,
    hash_file: Callable[[Path], str],
    changes: ChangeSet,
) -> None:
    """Même taille, mtime différent : seul le hash permet de trancher."""
    try:
        content_hash = hash_file(file.path)
    except OSError:
        # Devenu illisible : le pipeline tentera l'extraction et enregistrera l'erreur.
        changes.modified.append(KnownChange(file, document.id, None))
        return
    target = changes.touched if content_hash == document.content_hash else changes.modified
    target.append(KnownChange(file, document.id, content_hash))


def sha256_file(path: Path) -> str:
    """Hash SHA-256 des octets du fichier (et non du texte extrait), lu par blocs."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(_HASH_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()
