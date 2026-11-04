# 0003 — Recherche hybride BM25 + vectoriel fusionnée par RRF

- Date : 2026-10-08
- Statut : Accepté — paramètres fixés par l'ADR [0010](0010-parametres-de-fusion.md)

## Contexte

Les requêtes de l'utilisateur mélangent des termes exacts (noms de technologies, identifiants comme « API-472 », noms de personnes) et des formulations libres (« pourquoi j'ai abandonné MongoDB ? »), en français et en anglais. La conception initiale prévoyait une V0 en recherche sémantique seule.

## Options étudiées

- **Vectoriel seul** : bon sur les reformulations et le multilingue ; faible sur les termes exacts et les identifiants.
- **BM25 seul** : excellent sur les termes exacts, rapide, explicable ; échoue sur les synonymes et entre langues.
- **Hybride, fusion par scores normalisés et pondérés** : fin, mais les échelles de BM25 et du cosinus sont incomparables et la normalisation est fragile.
- **Hybride, fusion par RRF** : ne dépend que des rangs ; un seul paramètre (k) ; robuste.

## Décision

Recherche hybride dès la V0 : top 30 BM25 (FTS5) + top 30 vectoriel, fusionnés par **Reciprocal Rank Fusion** (`score = Σ 1/(k + rang)`, k = 60 par défaut), puis regroupement par document.

BM25 est construit **en premier** (étape 3) et sert de baseline à l'évaluation.

## Justification

- Les deux méthodes ont des faiblesses complémentaires.
- BM25 avec FTS5 coûte presque rien à mettre en place.
- RRF est simple, sans apprentissage, et évite le problème des échelles de scores.
- Construire BM25 d'abord donne une référence chiffrée pour mesurer l'apport réel du vectoriel.

## Conséquences

- Valeur de k, profondeur (30) et éventuelle pondération décidées par l'évaluation à l'étape 7 ; mettre à jour cet ADR ou en écrire un nouveau.
- Le reranker (cross-encoder) n'est **pas** inclus : il sera testé en V2 et gardé seulement si le gain mesuré justifie la latence.
- Les résultats affichent un classement, pas un pourcentage.
