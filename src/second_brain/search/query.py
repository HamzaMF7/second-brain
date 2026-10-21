"""Prétraitement des requêtes : de la phrase de l'utilisateur à une requête FTS5 sûre."""

import re
import unicodedata

from second_brain.search.stopwords import ENGLISH, FRENCH

# Suites de lettres ou de chiffres (Unicode), comme le découpage du tokenizer unicode61.
# `_` est exclu : unicode61 le traite comme un séparateur.
_WORD = re.compile(r"[^\W_]+")


def normalize_word(word: str) -> str:
    """Minuscules sans accents : « Où » → « ou ». Sert à comparer, pas à chercher."""
    decomposed = unicodedata.normalize("NFD", word.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_STOPWORDS = frozenset(normalize_word(word) for word in FRENCH | ENGLISH)


def to_fts5_query(text: str) -> str | None:
    """Requête FTS5 : mots utiles en minuscules, entre guillemets, combinés en OU.

    - les mots vides français et anglais sont retirés, sauf si la requête n'a que ça ;
    - les guillemets neutralisent la syntaxe FTS5 (AND, OR, NOT, *, ^, :, parenthèses) ;
    - OU plutôt que ET : un document n'a pas besoin de contenir tous les mots, et BM25
      classe quand même en tête ceux qui en contiennent le plus.
    Renvoie None s'il n'y a aucun mot à chercher.
    """
    words = list(dict.fromkeys(word.lower() for word in _WORD.findall(text)))  # sans doublons
    if not words:
        return None
    useful = [word for word in words if normalize_word(word) not in _STOPWORDS]
    return " OR ".join(f'"{word}"' for word in useful or words)
