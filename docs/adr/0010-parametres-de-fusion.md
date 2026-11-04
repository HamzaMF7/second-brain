# 0010 — Paramètres de la fusion hybride : RRF standard (k = 60, sans pondération, par chunk)

- Date : 2026-11-04
- Statut : Accepté
- Précise : [0003](0003-recherche-hybride-rrf.md) (paramètres à fixer par l'évaluation)

## Contexte

L'ADR 0003 retient une recherche hybride BM25 + vectoriel fusionnée par RRF et laisse à l'évaluation de l'étape 7 le choix de k, de la profondeur et d'une éventuelle pondération. La tâche 7.4 a construit `HybridRetriever`, devenu le mode de recherche par défaut ; la tâche 7.5 a mesuré ses variantes.

Évaluation (`eval/run_eval.py`, modèle `google/embeddinggemma-300m`, chunks de 400 tokens estimés, 10 documents par question, attendus non indexables retirés) sur les deux jeux retenus à la place d'un jeu personnel :

- **`samples`** (`eval/questions.yaml`) : 11 questions évaluables sur 6 PDF inventés, écrites pour piéger BM25 (synonymes, autre langue, singulier/pluriel, césure).
- **EDiTh / Véracier Industries** : 40 questions métier sur 1 004 PDF (fr 31, en 7, de 2), riches en codes et noms propres ; médiane de 20 documents attendus par question.

Résultats : `eval/results/2026-11-04_2156_samples.json` et `eval/results/2026-11-04_2157_edith.json`.

## Options étudiées

18 variantes hybrides : k ∈ {20, 60, 100} × poids (lexical, sémantique) ∈ {(1, 1), (2, 1), (1, 2)} × fusion par **chunk** ou par **document** (chaque liste réduite à ses documents avant RRF, pour qu'un document trouvé par deux chunks différents compte comme un consensus).

MRR@10 (extrait) :

| Méthode | samples | EDiTh | EDiTh fr | EDiTh en | EDiTh de |
|---|---|---|---|---|---|
| BM25 | 0,64 | **0,67** | **0,69** | 0,65 | 0,55 |
| Sémantique | 0,82 | 0,48 | 0,43 | 0,62 | 0,75 |
| Hybride k=20, (1,1), chunk | **0,86** | 0,61 | 0,61 | 0,54 | 0,75 |
| Hybride k=20, (2,1), chunk | 0,82 | 0,63 | 0,62 | 0,66 | 0,67 |
| **Hybride k=60, (1,1), chunk** | **0,86** | 0,57 | 0,57 | 0,54 | 0,75 |
| Hybride k=60, (2,1), chunk | **0,86** | 0,60 | 0,58 | 0,66 | 0,67 |
| Hybride k=60, (1,2), chunk | 0,82 | 0,56 | | | |
| Hybride k=60, (1,1), document | **0,86** | 0,54 | | | |

Par question, face à BM25 (MRR meilleur / moins bon) : hybride k=60 (1,1) : samples 5 / 0, EDiTh 6 / 12 ; hybride k=20 (2,1) : samples 4 / 0, EDiTh 4 / 8.

- **A. k = 60, poids (2, 1), par chunk** : meilleur score sur samples et moins de pertes sur EDiTh (0,60) ; mais un réglage de plus, choisi sur 40 questions parmi 18 essais.
- **B. RRF standard : k = 60, poids (1, 1), par chunk** : meilleur score sur samples, aucun paramètre ajusté ; mais le plus en retrait de BM25 sur EDiTh parmi les variantes par chunk (0,57).
- **C. BM25 par défaut, hybride en option** : le meilleur sur EDiTh, sans modèle à charger ; mais échoue là où l'étape 6 devait aider (synonymes, langue, morphologie : samples 0,64).
- **Fusion par document** : jamais meilleure que par chunk, nettement moins bonne sur EDiTh.

## Décision

**Option B.** Le mode de recherche par défaut est l'hybride en **RRF standard** : top 30 de chaque méthode (au moins k), **k = 60**, **sans pondération**, **fusion par chunk** puis regroupement par document. Valeurs dans `SearchConfig` (`rrf_k`, `rrf_weights`, `fusion`, `hybrid_candidates`).

## Justification

- **Pas de réglage fin sur des données trop petites** : entre variantes hybrides, les écarts restent sous 0,06 de MRR, soit 1 à 2 questions sur 40 ; avec 18 essais, le meilleur score peut être dû au hasard. Le RRF standard (k = 60 de Cormack et al., 2009, poids égaux) est le choix qui ne dépend pas de nos questions.
- **Le gain est net là où l'hybride doit servir** : sur samples, +0,22 de MRR face à BM25, aucune question perdue ; c'est le type de requête visé par le projet (« retrouve le document où… », reformulations, autre langue).
- **k compte peu** : 20, 60 et 100 donnent des résultats proches sur les deux jeux.
- **Fusion par chunk** : la fusion par document n'apporte rien (hypothèse du bonus de consensus non confirmée) ; explication probable : le sémantique remonte toujours des voisins, même hors sujet, qui obtiennent ainsi plus de faux consensus.

## Conséquences

- **Requêtes pleines de codes et de noms propres** : l'hybride est en retrait de BM25 (EDiTh 0,57 contre 0,67, 9 rangs 1 perdus sur 40). `--mode lexical` reste disponible, et sans chargement de modèle. Piste à mesurer plus tard : la pondération (2, 1), qui réduisait ces pertes.
- **Chaque recherche charge le modèle d'embeddings** (~2,5 s en CLI) ; à résoudre en V1, où l'API le gardera en mémoire.
- **La recherche hybride renvoie toujours des résultats** : le sémantique trouve toujours des voisins, même pour une requête sans réponse. Un seuil de pertinence serait à étudier (hors V0).
- **Le score RRF n'est pas affiché** : la CLI montre la provenance (`BM25 #3 · sens #1`) et le nombre de passages trouvés par BM25.
- **Piste V2 : reranker (cross-encodeur)** sur les 30 à 50 premiers candidats. Il ne change pas le rappel mais vise l'écart entre Hit@5 (0,70) et Hit@1 (0,45) de l'hybride sur EDiTh ; modèles multilingues disponibles dans fastembed (`BAAI/bge-reranker-v2-m3`, 0,57 Go en int8 ; `jinaai/jina-reranker-v2-base-multilingual`). À mesurer avec la latence (budget < 1 s, conception section 17).
- La fusion par document reste disponible (`SearchConfig.fusion`) pour être remesurée, sans être utilisée.
- **Réévaluer** si le modèle d'embeddings, le chunking (tâches 5.5 et 5.6) ou le jeu d'évaluation change, et avant d'ajouter un reranker (V2) : `uv run python eval/run_eval.py --set … --rrf-k 20 60 100 --weights 1,1 2,1 --fusion chunk`.
