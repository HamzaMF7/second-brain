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


def default_model_cache_dir() -> Path:
    """Cache des modèles d'embeddings : $XDG_CACHE_HOME/second-brain/models (Linux).

    fastembed utilise /tmp par défaut, vidé au redémarrage : le modèle serait retéléchargé,
    alors que le seul accès réseau autorisé est le téléchargement initial.
    """
    cache_home = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(cache_home) / "second-brain" / "models"


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    # Choisi à la tâche 6.7 (ADR 0009) ; potion-multilingual-128M = alternative légère.
    model_name: str = "google/embeddinggemma-300m"
    batch_size: int = 32  # textes envoyés ensemble au modèle
    cache_dir: Path = field(default_factory=default_model_cache_dir)


@dataclass(frozen=True, slots=True)
class SearchConfig:
    snippet_tokens: int = 24  # longueur des extraits, en mots (FTS5 : 64 au maximum)
    # Marqueurs des termes trouvés dans les extraits : caractères de contrôle absents des
    # documents (contrairement à [[ ]], fréquent en Markdown). La CLI les met en couleur.
    highlight_open: str = "\x02"
    highlight_close: str = "\x03"
    ellipsis: str = "…"
    # Regroupement par document : on demande fetch_factor × k chunks au retriever (doublé
    # tant qu'il manque des documents distincts), puis on garde le meilleur par document.
    fetch_factor: int = 5
    # Hybride : candidats demandés à chaque méthode (au moins k), puis fusion RRF.
    hybrid_candidates: int = 30
    rrf_k: int = 60  # provisoire : 20 / 60 / 100 mesurés à la tâche 7.5


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    # PROVISOIRE : 400 / 50 en attendant l'évaluation (tâches 5.5 et 5.6).
    max_tokens: int = 400  # rester sous la limite d'entrée des modèles d'embeddings (~512)
    overlap_tokens: int = 50  # repris du chunk précédent, à l'intérieur d'une même section/page
    # Compteur approximatif (mots × ratio) jusqu'au choix du modèle d'embeddings (étape 6).
    # Ratio prudent : le français fait environ 1,3 à 1,5 token par mot.
    tokens_per_word: float = 1.5
    # Indexer aussi « titre du document > section » (colonne chunks.context). Désactivé
    # tant que l'évaluation n'a pas mesuré son effet (tâche 5.5).
    context_prefix: bool = False
