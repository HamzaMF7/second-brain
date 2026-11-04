# 0004 — Embeddings multilingues locaux via ONNX

- Date : 2026-10-08
- Statut : Accepté — modèle précis choisi dans l'ADR [0009](0009-modele-embeddings-et-stockage-vectoriel.md)

## Contexte

Les documents sont majoritairement en français, avec de l'anglais. Les embeddings doivent être calculés localement (confidentialité). Le projet doit pouvoir devenir une application desktop distribuable. La conception initiale prévoyait Sentence Transformers.

## Options étudiées

- **Sentence Transformers (PyTorch)** : référence, très documentée. Mais PyTorch pèse plusieurs centaines de Mo à plusieurs Go : installation lente, packaging desktop lourd.
- **ONNX Runtime via fastembed** : mêmes familles de modèles, exécution CPU efficace, dépendances légères. Catalogue de modèles plus restreint.
- **API cloud d'embeddings** : excellente qualité, mais contraire au principe local et privé.
- **Modèles anglophones** (souvent les plus populaires) contre **modèles multilingues** (e5 multilingue, bge-m3…).

## Décision

Modèles **multilingues**, exécutés localement via **ONNX (fastembed)**, derrière l'interface `Embedder`. Le modèle précis est choisi à l'étape 6 en comparant 2 ou 3 candidats sur le jeu d'évaluation.

## Justification

- Corpus français et anglais, questions possibles dans une langue et documents dans l'autre.
- ONNX évite PyTorch : installation rapide maintenant, packaging réaliste plus tard.
- L'interface `Embedder` permet de changer de modèle ou de runtime sans toucher au reste.

## Conséquences

- Stocker le `model_id` (nom + version) avec chaque vecteur ; tout changement de modèle déclenche le recalcul des vecteurs concernés.
- Gérer les préfixes exigés par certains modèles (`query: ` / `passage: ` pour e5) dans l'implémentation, testé explicitement.
- Respecter la limite de tokens du modèle dans le chunking (voir étape 5).
- Critères de choix à l'étape 6 : Recall@5 et MRR par type de requête, temps d'indexation du corpus, taille sur disque, mémoire.
- Le téléchargement initial du modèle est le seul accès réseau autorisé.
