# 0009 — Modèle d'embeddings (embeddinggemma-300m) et stockage des vecteurs

- Date : 2026-11-03
- Statut : Accepté
- Précise : [0004](0004-embeddings-onnx-multilingues.md) (modèle à choisir) et le point « Cohérence » de [0002](0002-sqlite-base-unique.md)

## Contexte

L'ADR 0004 fixe des embeddings multilingues locaux via ONNX (fastembed), modèle à choisir à l'étape 6 sur quatre critères : qualité par type de requête, temps d'indexation, taille sur disque, mémoire. Trois candidats ont été retenus (tâche 6.2), de tailles très différentes, tous disponibles dans fastembed 0.9.1 :

| Modèle | Type | Dimension | Préfixes | Limite | Licence |
|---|---|---|---|---|---|
| `minishlab/potion-multilingual-128M` | statique (pas de réseau de neurones à l'inférence) | 256 | aucun | — | MIT |
| `google/embeddinggemma-300m` | transformeur, 300 M paramètres (2025) | 768 | `task: search result \| query: ` / `title: none \| text: ` | 2 048 tokens | Gemma Terms of Use |
| `intfloat/multilingual-e5-large` | transformeur, 560 M paramètres (2023) | 1 024 | `query: ` / `passage: ` | 512 tokens | MIT |

L'étape 4 (jeu d'évaluation du projet) a été reportée. La comparaison s'appuie donc sur deux jeux **exploratoires**, évalués par un script hors projet :

- **EDiTh / Véracier Industries** (benchmark public, LightOn) : 1 004 PDF d'entreprise inventés (FR majoritaire, EN, DE), 40 questions métier, documents attendus fournis. 179 PDF scannés (introuvables sans OCR) ; mesures sur les attendus indexables. Médiane de 20 documents attendus par question.
- **`samples/pdf`** : 6 PDF inventés, les 12 questions de la tâche 3.6, écrites pour piéger BM25 (synonymes, autre langue, singulier/pluriel, césure, scan).

Il faut aussi trancher **comment stocker les vecteurs** dans SQLite (ADR 0002) et comment leur calcul, lent, s'articule avec la règle « un document = une transaction ».

## Options étudiées

### Modèle

Mesures avec la recherche sémantique seule, résultats regroupés par document (chunks de 400 tokens estimés, chevauchement 50) :

| | EDiTh MRR | EDiTh Hit@1 | EDiTh Hit@5 | EDiTh nDCG@10 | samples MRR | samples rang 1 |
|---|---|---|---|---|---|---|
| BM25 (référence) | **0,67** | **0,62** | **0,78** | **0,30** | 0,58 | 6/12 |
| potion | 0,38 | 0,28 | 0,55 | 0,15 | 0,72 | 7/12 |
| embeddinggemma | 0,48 | 0,40 | 0,53 | 0,19 | **0,75** | **7/12** |
| e5-large | 0,28 | 0,25 | 0,33 | 0,10 | 0,63 | 5/12 |

MRR EDiTh par langue de la question : fr (31 questions) BM25 0,69 · potion 0,36 · gemma 0,43 · e5 0,22 ; en (7) BM25 0,65 · potion 0,39 · gemma 0,62 · e5 0,36.

Coûts (EDiTh, 6 375 chunks, CPU, 11 Go de RAM) :

| | Calcul des vecteurs | Par chunk | Mémoire max | Base compactée | Recherche (modèle chargé) |
|---|---|---|---|---|---|
| potion | 15 s | 2 ms | 1,4 Go | 26 Mo | 18 ms |
| embeddinggemma | 1 h 55 | 1,1 s | 4,6 Go | 43 Mo | 58 ms |
| e5-large | 3 h 26 | 1,9 s | 4,7 Go | 46 Mo | 92 ms |

Chargement du modèle à la première recherche : 2,5 à 2,9 s pour les trois.

- **A. potion** : 450 fois plus rapide à indexer, licence MIT ; mais nettement moins bon sur EDiTh (MRR 0,38).
- **B. embeddinggemma** : meilleur modèle sémantique sur les deux jeux, seul à égaler BM25 sur les questions anglaises d'EDiTh ; mais environ 1 s par chunk à l'indexation, 4,6 Go de mémoire, licence non open source.
- **C. e5-large** : dernier sur les deux jeux, le plus lent et le plus gourmand. Vérifié : vecteurs cohérents, préfixes appliqués, 30 chunks sur 6 375 seulement dépassent ses 512 tokens. L'écart n'est donc pas un bug, mais il reste inexpliqué (hypothèses : modèle plus ancien ; questions d'EDiTh courtes, en mots-clés, sans accents).

### Stockage des vecteurs

- **Table virtuelle `vec0` de sqlite-vec** : index dédié, prévu pour évoluer vers une recherche approchée. Mais dimension fixée à la création de la table (un seul modèle à la fois), pas de clé étrangère ni de purge en cascade.
- **Table ordinaire `chunk_vectors` + fonctions de sqlite-vec** (`vec_distance_cosine`) en force brute : n'importe quelle dimension, purge par `ON DELETE CASCADE`, contraintes `STRICT`. Mais pas d'index : coût linéaire en nombre de chunks.

### Calcul des vecteurs pendant l'indexation

- **Dans la transaction du document** (lecture stricte de l'ADR 0002) : tout ou rien par document. Mais une panne du modèle bloque l'indexation du texte, et la base reste verrouillée pendant le calcul (1 s par chunk avec embeddinggemma).
- **Phase séparée, comme un index dérivé** : le texte est indexé et cherchable par BM25 immédiatement ; les vecteurs sont calculés ensuite, par lots, pour tous les chunks qui n'en ont pas ou qui en ont un d'un autre modèle.

## Décision

1. Modèle par défaut : **`google/embeddinggemma-300m`** (fastembed, ONNX), réglable dans `EmbeddingConfig.model_name`.
2. Vecteurs dans une **table ordinaire `chunk_vectors`** (un vecteur par chunk, float32 little-endian, `model_id`), cherchés en **force brute** avec `vec_distance_cosine`.
3. Vecteurs calculés dans une **phase séparée** de l'indexation, traités comme un **index dérivé** : un vecteur peut être manquant, jamais périmé.

## Justification

- **Qualité d'abord** (principe 2) : embeddinggemma est premier des modèles sémantiques sur les deux jeux. Son avance sur potion est nette sur EDiTh (+0,10 de MRR, environ 4 questions sur 40), faible sur `samples` (+0,03).
- **Le sémantique complète BM25 plus qu'il ne le remplace** : sur EDiTh, BM25 reste devant (questions pleines de codes et de noms propres) ; sur `samples`, les trois modèles corrigent les échecs de BM25 (synonymes, langue, singulier/pluriel, césure). C'est l'argument de l'hybride (ADR 0003, étape 7) : le modèle retenu doit surtout bien faire ce que BM25 rate, ce que fait embeddinggemma.
- **Le coût est payé une fois** : l'indexation est incrémentale, seuls les nouveaux chunks sont calculés. Les recherches restent rapides (58 ms une fois le modèle chargé).
- **Choix réversible** : chaque vecteur porte un `model_id` = nom du modèle + signature de ses préfixes (`google/embeddinggemma-300m#9fec2002`). Changer de modèle ou de préfixes recalcule simplement les vecteurs concernés au prochain `index`.
- **Table ordinaire** : la force brute suffit à notre échelle (6 375 chunks : moins de 100 ms) et la purge en cascade garantit qu'un chunk supprimé ou redécoupé n'a jamais de vecteur orphelin.
- **Phase séparée** : le texte reste toujours indexé en une transaction par document (tout ou rien) ; un modèle en panne ou une interruption ne perd que des vecteurs, recalculés au passage suivant. Requête unique « chunks sans vecteur ou d'un autre modèle » pour les nouveaux chunks, la reprise après interruption et le changement de modèle.

## Conséquences

- **Point « Cohérence » de l'ADR 0002 précisé** : une transaction par document couvre texte, chunks et FTS ; les vecteurs sont enregistrés par lots dans des transactions séparées. La règle de CLAUDE.md (section 7) est à mettre à jour dans ce sens.
- **Première indexation longue** : environ 1 s par chunk sur ce poste (environ 2 h pour 1 000 PDF), 4,6 Go de mémoire pendant le calcul. Une barre de progression l'affiche ; `index` peut être interrompu et relancé sans perte.
- **Licence** : les *Gemma Terms of Use* ne sont pas une licence open source (conditions d'usage à transmettre en cas de redistribution). Sans effet en phase 1 ; **à réévaluer avant toute distribution**, comme PyMuPDF (ADR 0007). potion (MIT) reste l'alternative légère, à reprendre si le temps d'indexation devient un problème sur le corpus réel.
- **Taille des chunks** : `WordTokenCounter` estime 400 tokens ; le tokenizer d'embeddinggemma en compte 416 en médiane, 748 au maximum, toujours sous sa limite de 2 048. Le remplacer par le vrai tokenizer n'est donc pas urgent ; à reconsidérer avec les tâches 5.5 et 5.6.
- **Mesures exploratoires** : 40 + 12 questions, jeux écrits par d'autres ou par Claude, pas par l'utilisateur. **À réévaluer** avec le jeu d'évaluation de l'étape 4 et après l'hybride (étape 7) : c'est le gain apporté à l'hybride qui compte, pas le score sémantique seul.
- **Réévaluer le stockage** si la recherche vectorielle dépasse ~200 ms sur le corpus réel (seuil de l'ADR 0002) : passer à `vec0` ou à un index approché, derrière la même interface `Retriever`.
