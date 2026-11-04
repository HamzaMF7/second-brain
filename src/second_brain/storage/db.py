"""Ouverture de la base SQLite : seul endroit du code qui appelle sqlite3.connect (ADR 0008)."""

import sqlite3
from pathlib import Path

import sqlite_vec

from second_brain.storage.migrator import migrate


class VectorExtensionError(Exception):
    """L'extension sqlite-vec n'a pas pu être chargée dans la connexion."""


def _extension_path() -> str:
    """Chemin du fichier compilé de sqlite-vec (vec0.so sous Linux), fourni par le paquet."""
    return str(sqlite_vec.loadable_path())


def _load_vector_extension(conn: sqlite3.Connection) -> None:
    """Charge sqlite-vec : fonctions vec_* disponibles pour cette connexion seulement.

    Le chargement d'extensions est désactivé par défaut ; on ne l'ouvre que le temps de
    charger la nôtre, pour qu'aucune requête SQL ne puisse charger un autre fichier.
    """
    if not hasattr(conn, "enable_load_extension"):  # Python compilé sans ce support
        raise VectorExtensionError(
            "sqlite-vec : ce Python ne permet pas de charger des extensions SQLite"
        )
    try:
        conn.enable_load_extension(True)
        conn.load_extension(_extension_path())
    except sqlite3.OperationalError as error:
        raise VectorExtensionError(f"sqlite-vec : chargement impossible ({error})") from None
    finally:
        conn.enable_load_extension(False)


def connect(path: Path) -> sqlite3.Connection:
    """Connexion avec clés étrangères actives, sqlite-vec chargé, en mode transactionnel.

    PRAGMA foreign_keys est ignoré à l'intérieur d'une transaction : on l'exécute en
    autocommit, puis on passe en autocommit=False, où toute écriture se fait dans une
    transaction validée par `with conn:` (COMMIT) ou annulée en cas d'exception (ROLLBACK).
    """
    conn = sqlite3.connect(path, autocommit=True)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _load_vector_extension(conn)
    except VectorExtensionError:
        conn.close()
        raise
    conn.autocommit = False
    return conn


def open_database(path: Path) -> sqlite3.Connection:
    """Ouvre la base (en créant son dossier si besoin) et applique les migrations manquantes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    migrate(conn)
    return conn
