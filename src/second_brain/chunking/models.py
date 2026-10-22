"""Modèle d'un passage découpé."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """Un extrait EXACT de ExtractedDocument.text : text == doc.text[start:start + len(text)]."""

    index: int  # position dans le document (0, 1, 2…)
    text: str
    start: int  # position en caractères dans ExtractedDocument.text
    page: int | None  # page PDF ; None pour Markdown
    section: str | None  # chemin des titres : « Titre > Sous-titre »
    token_count: int
    # Préfixe indexé « titre > section » (option context_prefix) ; jamais affiché.
    context: str | None = None
