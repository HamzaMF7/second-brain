"""Configuration centralisée. Chaque réglage a une valeur par défaut documentée."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    # Un PDF dont la moyenne de caractères non blancs par page est inférieure à ce seuil
    # est considéré comme scanné. Une page de slides en compte en général plus de 100 ;
    # un scan peut porter un peu de texte parasite (numéro de page, filigrane).
    scan_threshold_chars_per_page: int = 50


@dataclass(frozen=True, slots=True)
class ScanConfig:
    """Exclusions par défaut du parcours des dossiers (CLAUDE.md, section 8)."""

    excluded_dirs: frozenset[str] = field(
        default_factory=lambda: frozenset({".git", "node_modules", "__pycache__", ".venv"})
    )
    temp_prefixes: tuple[str, ...] = ("~$", ".~lock")  # fichiers de verrou Office / LibreOffice
    max_file_size: int = 50 * 1024 * 1024  # octets ; au-delà, le fichier est ignoré


def default_database_path() -> Path:
    """Base par défaut, hors du dépôt : $XDG_DATA_HOME/second-brain/index.db (Linux).

    Elle contient le texte des documents ; la phase 2 utilisera les dossiers propres
    à chaque système (macOS, Windows).
    """
    data_home = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(data_home) / "second-brain" / "index.db"


@dataclass(frozen=True, slots=True)
class SearchConfig:
    snippet_tokens: int = 24  # longueur des extraits, en mots (FTS5 : 64 au maximum)
    # Marqueurs des termes trouvés dans les extraits : caractères de contrôle absents des
    # documents (contrairement à [[ ]], fréquent en Markdown). La CLI les met en couleur.
    highlight_open: str = "\x02"
    highlight_close: str = "\x03"
    ellipsis: str = "…"
