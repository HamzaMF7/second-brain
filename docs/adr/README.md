# Architecture Decision Records

Une page par décision structurante : le contexte, les options, le choix et pourquoi.
Un ADR accepté n'est jamais modifié sur le fond : si la décision change, on écrit un nouvel ADR qui le **remplace** et on met à jour le statut de l'ancien.

Brouillon d'un nouvel ADR dans Claude Code : `/adr <sujet>`.

## Index

| N° | Décision | Statut | Date |
|---|---|---|---|
| [0001](0001-python-et-cli-d-abord.md) | Python pour le cœur, CLI avant API et interface | Accepté | 2026-10-08 |
| [0002](0002-sqlite-base-unique.md) | SQLite comme base unique (tables, FTS5, vecteurs) | Accepté | 2026-10-08 |
| [0003](0003-recherche-hybride-rrf.md) | Recherche hybride BM25 + vectoriel fusionnée par RRF | Accepté, paramètres à mesurer | 2026-10-08 |
| [0004](0004-embeddings-onnx-multilingues.md) | Embeddings multilingues locaux via ONNX | Accepté, modèle à choisir | 2026-10-08 |
| [0005](0005-evaluation-des-la-v0.md) | Évaluation chiffrée dès la V0, arbitre des décisions | Accepté | 2026-10-08 |
| [0006](0006-local-first-et-confidentialite.md) | Local par défaut et règles de confidentialité | Accepté | 2026-10-08 |
| [0007](0007-bibliotheque-pdf.md) | Bibliothèque d'extraction PDF (PyMuPDF) | Accepté, à réévaluer avant distribution | 2026-10-12 |
| [0008](0008-sql-brut-sqlite3.md) | Accès aux données en SQL brut avec sqlite3 | Accepté | 2026-10-13 |
| [0009](0009-modele-embeddings-et-stockage-vectoriel.md) | Modèle d'embeddings (embeddinggemma-300m) et stockage des vecteurs | Accepté | 2026-11-03 |
| [0010](0010-parametres-de-fusion.md) | Paramètres de la fusion hybride (RRF standard) | Accepté | 2026-11-04 |

Décisions à venir : stratégie de chunking (tâches 5.5 et 5.6, après l'évaluation).

## Modèle

```markdown
# 00XX — Titre de la décision

- Date : AAAA-MM-JJ
- Statut : Proposé | Accepté | Remplacé par 00YY

## Contexte
Quel problème, quelles contraintes.

## Options étudiées
- **Option A** : avantages / inconvénients
- **Option B** : avantages / inconvénients

## Décision
Ce qui est choisi, en une phrase.

## Justification
Pourquoi, avec les mesures si possible.

## Conséquences
Ce que ça implique, ce qu'il faudra surveiller, quand réévaluer.
```
