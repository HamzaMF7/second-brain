"""Comptage des tokens : approximatif aujourd'hui, tokenizer du modèle à l'étape 6."""

import math
from abc import ABC, abstractmethod


class TokenCounter(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Identifie le compteur (un autre tokenizer découpe différemment)."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Nombre de tokens du texte pour le modèle visé."""


class WordTokenCounter(TokenCounter):
    """Approximation : nombre de mots × ratio, arrondi au-dessus (surestime volontairement)."""

    def __init__(self, tokens_per_word: float = 1.5) -> None:
        self.tokens_per_word = tokens_per_word

    @property
    def id(self) -> str:
        return f"words×{self.tokens_per_word:g}"

    def count(self, text: str) -> int:
        return math.ceil(len(text.split()) * self.tokens_per_word)
