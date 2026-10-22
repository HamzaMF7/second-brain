"""Contrat commun aux stratégies de découpage."""

from abc import ABC, abstractmethod

from second_brain.chunking.models import Chunk
from second_brain.extraction.models import ExtractedDocument


class Chunker(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Signature des réglages, enregistrée avec chaque document (comme model_id pour
        les embeddings) : si elle change, les documents sont redécoupés."""

    @abstractmethod
    def chunk(self, doc: ExtractedDocument) -> list[Chunk]:
        """Découpe le document en passages, dans l'ordre du texte."""
