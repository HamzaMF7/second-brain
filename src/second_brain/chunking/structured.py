"""Découpage qui respecte la structure, puis récursif.

1. Blocs structurels : une section Markdown (du titre au titre suivant) ou une page PDF.
   Un chunk ne traverse jamais deux blocs.
2. Un bloc trop grand est redécoupé : paragraphes, puis phrases, puis lignes, puis mots.
3. Les morceaux consécutifs d'un bloc sont regroupés jusqu'à `max_tokens` ; chaque nouveau
   chunk reprend les derniers morceaux du précédent dans la limite de `overlap_tokens`.

Tout est manipulé en positions (début, fin) dans ExtractedDocument.text : chaque chunk est
un extrait exact du texte, jamais un texte recomposé.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from second_brain.chunking.base import Chunker
from second_brain.chunking.models import Chunk
from second_brain.chunking.tokens import TokenCounter, WordTokenCounter
from second_brain.config import ChunkingConfig
from second_brain.extraction.models import PAGE_SEPARATOR, ExtractedDocument

Span = tuple[int, int]  # (début, fin) dans le texte du document

_PARAGRAPH = re.compile(r"\n[ \t]*\n\s*")
_LINE = re.compile(r"\n\s*")
_WORD = re.compile(r"\s+")
# Fin de phrase : ponctuation finale, guillemets ou parenthèses fermants éventuels, espace.
_SENTENCE_END = re.compile(r"[.!?…]+(?:\s*[»\"”’)\]])*\s+")
_LAST_WORD = re.compile(r"(\S+)$")
# Mots suivis d'un point qui ne terminent pas une phrase (comparés en minuscules).
_ABBREVIATIONS_TEXT = """
    m mme mlle mm dr pr me st ste etc ex cf env fig vol art chap éd p pp no n°
    mr mrs ms vs e.g i.e
"""
_ABBREVIATIONS = frozenset(_ABBREVIATIONS_TEXT.split())


@dataclass(frozen=True, slots=True)
class _Block:
    start: int
    end: int
    page: int | None
    section: str | None


class StructuredChunker(Chunker):
    def __init__(
        self, config: ChunkingConfig | None = None, counter: TokenCounter | None = None
    ) -> None:
        self.config = config or ChunkingConfig()
        self.counter = counter or WordTokenCounter(self.config.tokens_per_word)

    @property
    def id(self) -> str:
        c = self.config
        context = int(c.context_prefix)
        return (
            f"structured:max{c.max_tokens}:overlap{c.overlap_tokens}:ctx{context}:{self.counter.id}"
        )

    def chunk(self, doc: ExtractedDocument) -> list[Chunk]:
        text = doc.text
        chunks: list[Chunk] = []
        for block in _blocks(doc):
            context = _context(doc, block.section) if self.config.context_prefix else None
            atoms = [
                span
                for span in self._split(text, block.start, block.end, level=0)
                if text[span[0] : span[1]].strip()
            ]
            for span in self._pack(text, atoms):
                start, end = _strip(text, span)
                chunk_text = text[start:end]
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=chunk_text,
                        start=start,
                        page=block.page,
                        section=block.section,
                        token_count=self.counter.count(chunk_text),
                        context=context,
                    )
                )
        return chunks

    def _tokens(self, text: str, span: Span) -> int:
        return self.counter.count(text[span[0] : span[1]])

    def _split(self, text: str, start: int, end: int, level: int) -> list[Span]:
        """Redécoupe [start, end) avec des séparateurs de plus en plus fins, si besoin."""
        if level >= len(_SPLITTERS) or self._tokens(text, (start, end)) <= self.config.max_tokens:
            return [(start, end)]
        spans: list[Span] = []
        for piece_start, piece_end in _SPLITTERS[level](text, start, end):
            spans.extend(self._split(text, piece_start, piece_end, level + 1))
        return spans

    def _pack(self, text: str, atoms: list[Span]) -> list[Span]:
        """Regroupe les morceaux consécutifs ; chevauchement par morceaux entiers."""
        packed: list[Span] = []
        current: list[Span] = []
        tokens = 0
        for atom in atoms:
            atom_tokens = self._tokens(text, atom)
            if current and tokens + atom_tokens > self.config.max_tokens:
                packed.append((current[0][0], current[-1][1]))
                current, tokens = self._overlap(text, current)
                if tokens + atom_tokens > self.config.max_tokens:
                    current, tokens = [], 0
            current.append(atom)
            tokens += atom_tokens
        if current:
            packed.append((current[0][0], current[-1][1]))
        return packed

    def _overlap(self, text: str, previous: list[Span]) -> tuple[list[Span], int]:
        """Derniers morceaux du chunk précédent à reprendre (jamais son premier : on avance)."""
        carried: list[Span] = []
        tokens = 0
        for atom in reversed(previous[1:]):
            atom_tokens = self._tokens(text, atom)
            if tokens + atom_tokens > self.config.overlap_tokens:
                break
            carried.insert(0, atom)
            tokens += atom_tokens
        return carried, tokens


def _blocks(doc: ExtractedDocument) -> list[_Block]:
    """Sections (avec le chemin des titres) si le document en a, sinon pages."""
    text = doc.text
    if doc.sections:
        sections = sorted(doc.sections, key=lambda s: s.offset)
        blocks: list[_Block] = []
        if sections[0].offset > 0:
            blocks.append(_Block(0, sections[0].offset, sections[0].page, None))
        path: list[tuple[int, str]] = []  # (niveau, titre) des sections englobantes
        for i, section in enumerate(sections):
            while path and path[-1][0] >= section.level:
                path.pop()
            path.append((section.level, section.title))
            end = sections[i + 1].offset if i + 1 < len(sections) else len(text)
            label = " > ".join(title for _, title in path)
            blocks.append(_Block(section.offset, end, section.page, label))
        return blocks

    blocks = []
    offset = 0
    for page in doc.pages:
        blocks.append(_Block(offset, offset + len(page.text), page.number, None))
        offset += len(page.text) + len(PAGE_SEPARATOR)
    return blocks


def _context(doc: ExtractedDocument, section: str | None) -> str:
    """« titre du document > section », sans répéter le titre s'il ouvre déjà la section.

    Sans titre dans les métadonnées, le nom du fichier en tient lieu (souvent parlant).
    """
    title = doc.title or doc.path.stem
    parts = section.split(" > ") if section else []
    if parts and parts[0] == title:
        parts = parts[1:]
    return " > ".join([title, *parts])


def _cut(start: int, end: int, cuts: list[int]) -> list[Span]:
    """Découpe [start, end) aux positions données (les séparateurs restent à gauche)."""
    bounds = [start, *(c for c in cuts if start < c < end), end]
    return [(a, b) for a, b in zip(bounds, bounds[1:], strict=False) if a < b]


def _regex_splitter(pattern: re.Pattern[str]) -> Callable[[str, int, int], list[Span]]:
    def split(text: str, start: int, end: int) -> list[Span]:
        return _cut(start, end, [m.end() for m in pattern.finditer(text, start, end)])

    return split


def _sentence_ends(text: str, start: int = 0, end: int | None = None) -> list[int]:
    end = len(text) if end is None else end
    cuts = []
    for match in _SENTENCE_END.finditer(text, start, end):
        if match.group().startswith(".") and _is_abbreviation(text[start : match.start()]):
            continue
        cuts.append(match.end())
    return cuts


def _is_abbreviation(before: str) -> bool:
    """Le mot qui précède le point est-il une abréviation ou une initiale (« M. », « J. ») ?"""
    match = _LAST_WORD.search(before)
    if match is None:
        return False
    word = match.group(1).lstrip("(«\"'").lower()
    return (len(word) == 1 and word.isalpha()) or word in _ABBREVIATIONS


def _split_sentences_span(text: str, start: int, end: int) -> list[Span]:
    return _cut(start, end, _sentence_ends(text, start, end))


def split_sentences(text: str) -> list[str]:
    """Phrases du texte, chacune avec sa ponctuation finale et l'espace qui suit."""
    return [text[a:b] for a, b in _split_sentences_span(text, 0, len(text))]


def _strip(text: str, span: Span) -> Span:
    """Retire les blancs aux deux extrémités en ajustant les positions."""
    start, end = span
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


# Phrases avant lignes : dans un PDF, chaque ligne visuelle finit par « \n », souvent au
# milieu d'une phrase (voire d'un mot coupé par une césure). Les lignes ne servent qu'en
# recours, pour les textes sans ponctuation (code, listes, slides).
_SPLITTERS: list[Callable[[str, int, int], list[Span]]] = [
    _regex_splitter(_PARAGRAPH),
    _split_sentences_span,
    _regex_splitter(_LINE),
    _regex_splitter(_WORD),
]
