# Rétrospective V0

> 2026-10-11 → 2026-11-04 · étapes 0 à 7 · 10 ADR · 360 tests.
> Sources : `docs/journal.md`, `docs/adr/`, `eval/results/`.

## Ce qui a marché

- **Les interfaces ont tenu leur promesse.** Sémantique, hybride et trois modèles d'embeddings ajoutés sans réécrire l'extraction, le stockage ni BM25 : `HybridRetriever` ne fait que combiner deux `Retriever` existants.
- **Tests d'abord, un vrai filet.** De 56 tests (étape 1) à 360, sans vrai modèle, en 15 s. Plusieurs pièges attrapés par les tests avant toute utilisation : PRAGMA ignoré dans une transaction, synchronisation FTS *external content*, CLI qui chargeait le vrai modèle sans le dire.
- **SQLite comme base unique.** Texte, FTS5 et vecteurs dans un seul fichier, purge en cascade : aucune désynchronisation rencontrée.
- **« Mesurer, pas supposer » a renversé trois intuitions** : e5-large, le plus gros modèle, arrive dernier ; la fusion par document (bonus de consensus attendu) fait moins bien ; l'hybride ne bat pas BM25 sur les requêtes pleines de codes.
- **Confidentialité tenue dès le départ** : jamais de contenu dans les logs ni les erreurs (testé), fixtures inventées, aucun appel réseau.

## Ce qui a été plus dur que prévu

- **L'extraction PDF.** Aucune bibliothèque ne remet deux colonnes dans l'ordre ; les césures (« pro-venance ») cassent BM25. Une partie des échecs de recherche vient de l'extraction, pas du classement.
- **Les pièges silencieux de SQLite** : PRAGMA ignoré, DDL non annulé, FTS *external content* qui se corrompt sans message.
- **Le coût réel des embeddings sur CPU** : 15 s (potion), 1 h 55 (embeddinggemma), 3 h 26 (e5-large) pour EDiTh, plus une nuit perdue à cause de la mise en veille.
- **Construire une évaluation crédible** : trouver un benchmark (dépôt mal nommé, 263 fichiers macOS parasites), puis constater que `samples` et EDiTh donnent des gagnants opposés.

## Ce que je referais autrement

1. **L'évaluation avant le chunking.** Reporter l'étape 4 a laissé la taille de chunk (5.5 / 5.6) et les mots vides sans mesure, et le modèle a été choisi avec un script hors projet. Le banc d'évaluation, arrivé à la 7.5, aurait servi dès l'étape 5.
2. **Lancer `index` / `search` sur le vrai corpus beaucoup plus tôt.** La V0 n'a jamais vu mes documents.
3. **Un modèle léger pour développer, le gros pour mesurer.** Fait avec potion, mais trop tard : la 6.7 a coûté une nuit.
4. **Les scripts exploratoires dans le projet dès le départ**, pas dans un brouillon qui peut disparaître.

## Ce que les chiffres disent des priorités pour la V1

| Chiffre | Ce qu'il implique |
|---|---|
| **17 %** des attendus EDiTh sont des scans (144 / 825), introuvables par toutes les méthodes | **OCR** : première source de rappel perdu, confirmée par les données |
| **2,5 à 3,7 s** par recherche, surtout le chargement du modèle | **API qui garde le modèle en mémoire**, indispensable pour un usage quotidien |
| **1 s par chunk** à l'indexation (≈ 2 h pour 1 000 PDF) | **File watcher** en tâche de fond, sans bloquer |
| Hybride : MRR 0,57 contre 0,67 (BM25) sur les codes, 0,86 contre 0,64 sur les questions naturelles | Piste V2 : **reranker**, qui vise l'écart Hit@5 (0,70) / Hit@1 (0,45) ; en attendant, `--mode lexical` pour les codes |
| Taille de chunk, préfixe de contexte, mots vides, césures : **jamais mesurés** | Mesures presque gratuites maintenant que `eval/run_eval.py` existe : **en début de V1**, avant d'ajouter des formats |
