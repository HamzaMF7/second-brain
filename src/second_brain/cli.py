"""Point d'entrée de la ligne de commande second-brain."""

import logging
import sqlite3
import sys
import textwrap
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Protocol

import typer

from second_brain.chunking.structured import StructuredChunker
from second_brain.config import (
    ChunkingConfig,
    EmbeddingConfig,
    SearchConfig,
    default_database_path,
)
from second_brain.embeddings.base import Embedder
from second_brain.embeddings.fastembed_embedder import FastEmbedEmbedder
from second_brain.extraction.errors import ExtractionError
from second_brain.extraction.registry import default_registry
from second_brain.indexing.pipeline import EmbeddingError, index_folder
from second_brain.search.base import Retriever
from second_brain.search.grouping import search_documents
from second_brain.search.lexical import LexicalRetriever
from second_brain.search.semantic import SemanticRetriever
from second_brain.storage.db import open_database
from second_brain.storage.vectors import chunks_needing_vectors

PREVIEW_CHARS = 500  # longueur de l'aperçu affiché par `extract`
CHUNK_PREVIEW_CHARS = 300  # début + fin d'un chunk affichés par `chunks` (sans --full)

DbOption = Annotated[
    Path | None,
    typer.Option(
        "--db",
        envvar="SECOND_BRAIN_DB",
        help="Fichier de la base (défaut : ~/.local/share/second-brain/index.db).",
    ),
]


class SearchMode(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"


app = typer.Typer(
    help="Mémoire personnelle locale interrogeable en langage naturel.",
    no_args_is_help=True,
    add_completion=False,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(version("second-brain"))
        raise typer.Exit()


@app.callback()
def main(
    show_version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_show_version,
            is_eager=True,
            help="Affiche la version et quitte.",
        ),
    ] = False,
) -> None:
    """Options globales, communes à toutes les sous-commandes."""


@app.command()
def index(
    folder: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True, help="Dossier à indexer."),
    ],
    db: DbOption = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Journalise chaque fichier traité.")
    ] = False,
) -> None:
    """Indexe un dossier : ajoute, met à jour et purge les documents."""
    db_path = db or default_database_path()
    embedding_config = EmbeddingConfig()
    embedder = _make_embedder(embedding_config)
    conn = open_database(db_path)
    try:
        with _verbose_logging(verbose), ExitStack() as stack:
            report = index_folder(
                conn,
                folder,
                default_registry(),
                on_progress=_progress_bar(stack, "Indexation"),
                embedder=embedder,
                embedding_config=embedding_config,
                on_embed_progress=_progress_bar(stack, "Embeddings"),
            )
    except EmbeddingError as exc:
        typer.echo(
            f"Erreur : {exc}. Le texte est indexé ; relancez `index` pour finir les vecteurs.",
            err=True,
        )
        raise typer.Exit(code=1) from None
    finally:
        conn.close()

    touched = f"  (dont {report.touched} : métadonnées seules)" if report.touched else ""
    skipped = ", ".join(f"{reason} : {n}" for reason, n in report.skipped.most_common())
    lines = [
        ("Dossier", str(folder.resolve())),
        ("Base", str(db_path)),
        ("Ajoutés", str(report.added)),
        ("Modifiés", str(report.modified)),
        ("Supprimés", str(report.deleted)),
        ("Inchangés", f"{report.unchanged + report.touched}{touched}"),
        ("PDF scannés", f"{report.scanned_pdfs}  (ajoutés ou modifiés, sans texte exploitable)"),
        ("Erreurs", str(report.errors) + ("  (détails : --verbose)" if report.errors else "")),
        ("Ignorés", f"{report.skipped.total()}" + (f"  ({skipped})" if skipped else "")),
        (
            "Vecteurs",
            f"{report.embedded} calculés en {report.embedding_seconds:.1f} s"
            f"  ({embedder.model_id})",
        ),
        ("Durée", f"{report.seconds:.1f} s"),
    ]
    for label, value in lines:
        typer.echo(f"{label:<12}: {value}")


class _Updatable(Protocol):
    """Ce que la commande utilise de la barre de progression de Typer."""

    def update(self, n_steps: int) -> None: ...


def _make_embedder(config: EmbeddingConfig) -> Embedder:
    """Point unique de construction du modèle (remplacé par un faux dans les tests de la CLI).

    Le modèle n'est chargé, voire téléchargé, qu'au premier vecteur à calculer.
    """
    return FastEmbedEmbedder(config)


def _progress_bar(stack: ExitStack, label: str) -> Callable[[int, int], None]:
    """Callback de progression qui ouvre la barre au premier appel (le total est alors connu)."""
    bars: list[_Updatable] = []
    shown = 0

    def on_progress(done: int, total: int) -> None:
        nonlocal shown
        if not bars:
            bars.append(
                stack.enter_context(typer.progressbar(length=total, label=label, file=sys.stderr))
            )
        bars[0].update(done - shown)
        shown = done

    return on_progress


@contextmanager
def _verbose_logging(enabled: bool) -> Iterator[None]:
    """Affiche les logs du paquet sur stderr le temps d'une commande."""
    if not enabled:
        yield
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("second_brain")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Ce que tu cherches, en langage naturel.")],
    k: Annotated[int, typer.Option("-k", min=1, help="Nombre de résultats.")] = 10,
    db: DbOption = None,
    all_chunks: Annotated[
        bool,
        typer.Option("--all-chunks", help="Un résultat par chunk, sans regroupement par document."),
    ] = False,
    mode: Annotated[
        SearchMode,
        typer.Option(
            "--mode", help="lexical : mots exacts (BM25) ; semantic : sens proche (embeddings)."
        ),
    ] = SearchMode.LEXICAL,
) -> None:
    """Recherche dans les documents indexés, par mots (BM25) ou par sens (embeddings)."""
    db_path = db or default_database_path()
    if not db_path.exists():  # ne pas créer une base vide sur une faute de frappe
        typer.echo(
            f"Erreur : base introuvable ({db_path}). Lance d'abord `second-brain index <dossier>`.",
            err=True,
        )
        raise typer.Exit(code=1)

    config = SearchConfig()
    conn = open_database(db_path)
    try:
        start = time.perf_counter()
        retriever: Retriever
        if mode is SearchMode.SEMANTIC:
            embedder = _make_embedder(EmbeddingConfig())
            _warn_missing_vectors(conn, embedder.model_id)
            retriever = SemanticRetriever(conn, embedder, config)
        else:
            retriever = LexicalRetriever(conn, config)
        if all_chunks:
            results = retriever.search(query, k)
        else:
            results = search_documents(retriever, query, k, config.fetch_factor)
        elapsed_ms = (time.perf_counter() - start) * 1000
    finally:
        conn.close()

    if not results:
        typer.echo(f"Aucun résultat pour « {query} » ({elapsed_ms:.0f} ms).")
        return
    for rank, result in enumerate(results, start=1):
        typer.echo(f"{rank:>2}. {typer.style(result.path.name, bold=True)}  {result.score:.2f}")
        typer.echo(f"    {_highlight(result.snippet, config)}")
        typer.echo(typer.style(f"    {result.path}", dim=True))
    plural = "s" if len(results) > 1 else ""
    typer.echo(f"\n{len(results)} résultat{plural} en {elapsed_ms:.0f} ms")


def _warn_missing_vectors(conn: sqlite3.Connection, model_id: str) -> None:
    """Index incomplet (interruption, changement de modèle) : ces chunks seraient ignorés."""
    missing = len(chunks_needing_vectors(conn, model_id))
    if missing:
        typer.echo(
            f"Attention : {missing} chunk(s) sans vecteur pour {model_id}, ignorés."
            " Relance `second-brain index <dossier>`.",
            err=True,
        )


def _highlight(snippet: str, config: SearchConfig) -> str:
    """Extrait sur une ligne, termes trouvés en couleur (retirée hors terminal par echo)."""
    text = " ".join(snippet.split())
    parts = text.split(config.highlight_open)
    pieces = [parts[0]]
    for part in parts[1:]:
        term, _, rest = part.partition(config.highlight_close)
        pieces.append(typer.style(term, fg="yellow", bold=True) + rest)
    return "".join(pieces)


@app.command()
def extract(
    path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Fichier à extraire."),
    ],
) -> None:
    """Affiche le titre, les pages et le début du texte extrait d'un fichier."""
    try:
        doc = default_registry().for_path(path).extract(path)
    except ExtractionError as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Fichier   : {path.name}")
    typer.echo(f"Titre     : {doc.title or '(aucun)'}")
    typer.echo(f"Pages     : {len(doc.pages)}")
    typer.echo(f"Scanné    : {'oui' if doc.is_scanned else 'non'}")
    text = doc.text
    typer.echo(f"\n--- {min(len(text), PREVIEW_CHARS)} premiers caractères sur {len(text)} ---")
    typer.echo(text[:PREVIEW_CHARS])


@app.command()
def chunks(
    path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Fichier à découper."),
    ],
    max_tokens: Annotated[
        int | None, typer.Option("--max-tokens", min=1, help="Taille maximale d'un chunk.")
    ] = None,
    overlap: Annotated[
        int | None, typer.Option("--overlap", min=0, help="Chevauchement, en tokens.")
    ] = None,
    context: Annotated[
        bool, typer.Option("--context", help="Calcule le préfixe « titre > section ».")
    ] = False,
    full: Annotated[bool, typer.Option("--full", help="Affiche le texte complet.")] = False,
) -> None:
    """Affiche le découpage d'un fichier en chunks, sans toucher à la base."""
    defaults = ChunkingConfig()
    config = ChunkingConfig(
        max_tokens=max_tokens if max_tokens is not None else defaults.max_tokens,
        overlap_tokens=overlap if overlap is not None else defaults.overlap_tokens,
        context_prefix=context,
    )
    try:
        doc = default_registry().for_path(path).extract(path)
    except ExtractionError as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=1) from None

    pieces = StructuredChunker(config).chunk(doc)
    for piece in pieces:
        where = [f"tokens : {piece.token_count}", f"position : {piece.start}"]
        if piece.page is not None:
            where.insert(0, f"page {piece.page}")
        typer.echo(typer.style(f"#{piece.index}", bold=True) + "  " + " · ".join(where))
        if piece.section:
            typer.echo(f"    section : {piece.section}")
        if piece.context:
            typer.echo(f"    contexte : {piece.context}")
        text = piece.text if full else _shorten(piece.text, CHUNK_PREVIEW_CHARS)
        typer.echo(textwrap.indent(text, "    │ "))
        typer.echo()

    sizes = [p.token_count for p in pieces]
    summary = f"{len(pieces)} chunk{'s' if len(pieces) > 1 else ''}"
    if sizes:
        summary += f" · tokens min {min(sizes)} / moy {sum(sizes) // len(sizes)} / max {max(sizes)}"
    summary += f" · réglages : {config.max_tokens} tokens, chevauchement {config.overlap_tokens}"
    if doc.is_scanned:
        summary += " · document scanné : aucun texte exploitable"
    typer.echo(summary)


def _shorten(text: str, limit: int) -> str:
    """Début et fin d'un texte trop long, pour voir où le chunk commence et s'arrête."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n[…]\n{text[-half:]}"
