"""Table des modèles connus et de leurs préfixes.

fastembed n'ajoute aucun préfixe (vérifié dans la version 0.9.1) : un oubli ne lève
aucune erreur mais dégrade les résultats. On refuse donc tout modèle absent de la table
plutôt que de deviner.
"""

import hashlib
from dataclasses import dataclass


class UnknownModelError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str  # nom fastembed
    dimension: int
    query_prefix: str
    passage_prefix: str

    @property
    def signature(self) -> str:
        """Empreinte courte de la façon d'appeler le modèle : changer un préfixe la change."""
        raw = f"{self.query_prefix}\0{self.passage_prefix}".encode()
        return hashlib.sha256(raw).hexdigest()[:8]


# Candidats retenus à la tâche 6.2 ; préfixes repris de la description fastembed de chaque modèle.
MODEL_SPECS: dict[str, ModelSpec] = {
    spec.name: spec
    for spec in (
        ModelSpec("intfloat/multilingual-e5-large", 1024, "query: ", "passage: "),
        ModelSpec(
            "google/embeddinggemma-300m",
            768,
            "task: search result | query: ",
            "title: none | text: ",
        ),
        ModelSpec("minishlab/potion-multilingual-128M", 256, "", ""),
    )
}


def get_spec(model_name: str) -> ModelSpec:
    try:
        return MODEL_SPECS[model_name]
    except KeyError:
        known = ", ".join(sorted(MODEL_SPECS))
        raise UnknownModelError(
            f"modèle d'embeddings inconnu : {model_name} (connus : {known})"
        ) from None
