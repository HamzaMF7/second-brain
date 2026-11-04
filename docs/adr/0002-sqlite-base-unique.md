# 0002 — SQLite comme base unique (tables, FTS5, vecteurs)

- Date : 2026-10-08
- Statut : Accepté — point « Cohérence » précisé par l'ADR [0009](0009-modele-embeddings-et-stockage-vectoriel.md) (vecteurs calculés dans une phase séparée)

## Contexte

Il faut stocker les métadonnées des documents, le texte des chunks, un index plein texte (BM25) et des vecteurs. Le système doit tourner en local, être simple à installer et, plus tard, distribuable dans une application desktop. Le volume visé est de quelques milliers à quelques centaines de milliers de chunks.

## Options étudiées

- **SQLite + Qdrant (serveur ou Docker)** — proposé dans la conception initiale. Qdrant est performant et riche en filtres. Mais c'est un second processus à lancer et à distribuer, et deux bases à garder synchronisées (un document purgé dans SQLite peut rester dans Qdrant).
- **SQLite + Qdrant en mode local/embarqué** — pas de serveur, mais toujours deux sources de données à synchroniser.
- **SQLite + LanceDB** — embarqué, efficace, mais toujours deux stockages.
- **SQLite seul : FTS5 + sqlite-vec** — tout dans un fichier, transactions communes. Recherche vectorielle en force brute, moins scalable qu'un index ANN.

## Décision

Un seul fichier SQLite contenant les tables relationnelles, l'index FTS5 (`tokenize = 'unicode61 remove_diacritics 2'`) et les vecteurs via l'extension **sqlite-vec**.

## Justification

- **Cohérence** : indexation d'un document = une transaction couvrant texte, FTS et vecteurs. La purge en cascade supprime tout d'un coup. Pas de désynchronisation possible.
- **Simplicité** : rien à lancer, rien à configurer, base inspectable avec n'importe quel outil SQLite.
- **Distribution** : un fichier et une extension, compatible avec une app desktop.
- **Performance suffisante** : à quelques milliers de chunks, la force brute répond en millisecondes.
- Tokenizer `unicode61 remove_diacritics 2` : gère les accents français ; `porter` est réservé à l'anglais.

## Conséquences

- Toujours activer `PRAGMA foreign_keys = ON` et passer par des migrations numérotées.
- FTS5 en mode « external content », synchronisée par triggers ; tests de purge obligatoires.
- Vérifier au démarrage que sqlite-vec se charge, avec un message d'erreur clair sinon.
- **Réévaluer** si la recherche vectorielle dépasse ~200 ms sur le corpus réel, ou si le volume dépasse quelques centaines de milliers de chunks : passer alors à un index ANN (Qdrant local, LanceDB) derrière la même interface `Retriever`.
