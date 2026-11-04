# Journal de bord

> Une entrée par fin d'étape : ce qui a été fait, appris, ce qui a été difficile, les chiffres.

## 2026-10-12 — Étape 1 : extraction

**Fait**
- Modèles `ExtractedDocument` / `Page` / `Section` (dataclasses immuables), avec `Section.offset`
  pour que le futur chunking sache où commence chaque section.
- Pattern Strategy : interface `DocumentExtractor`, registre `ExtractorRegistry`,
  `default_registry()` comme unique endroit qui liste les formats.
- Extracteurs TXT et Markdown : encodage UTF-8 → cp1252 → Latin-1, normalisation NFC,
  titres Markdown hors blocs de code.
- Corpus de 6 PDF inventés (colonnes, césures, ligatures, slides, export façon Word, scan, mixte)
  et comparatif PyMuPDF / pypdf → ADR 0007 : PyMuPDF.
- `PdfExtractor` : une page par page, ligatures développées, détection des scans
  (< 50 caractères/page en moyenne), erreurs typées sans contenu.
- Commande `second-brain extract` et script `extract_all.py` (rapport sans contenu).
- 56 tests.

**Appris**
- Un PDF est un format de dessin : ordre de lecture, mots et lignes sont reconstruits.
- Un encodage transforme des octets en caractères ; UTF-8 est strict, donc essayé en premier ;
  Latin-1 accepte tout, donc en dernier.
- NFC : un même « é » peut s'écrire de deux façons ; sans normalisation, la recherche échoue en silence.
- `raise ... from None` coupe la chaîne d'exceptions, utile quand le message d'origine peut
  contenir du contenu.
- Ordre des `except` : le plus spécifique d'abord.
- Licences : l'AGPL est contaminante à la distribution, pas à l'usage personnel.

**Difficile**
- Aucune bibliothèque ne remet deux colonnes dans l'ordre ; `TEXT_DEHYPHENATE` de MuPDF
  n'a eu aucun effet.
- Trois fois, un test était faux et le code juste : vérifier qui a tort avant de corriger.
- Un PDF sans permission était signalé « corrompu » : MuPDF masquait la vraie cause.

**Chiffres**
- Corpus inventé : PyMuPDF 5 à 15× plus rapide que pypdf ; pypdf colle des lignes
  (`Conclusionsouvient`). Pas encore d'évaluation de recherche (étape 4).

## 2026-10-13 — Étape 2 : stockage et indexation

**Fait**
- ADR 0008 : SQL brut avec `sqlite3`, confiné à `storage/`.
- Schéma initial (tables `STRICT`) et migrations numérotées `NNN_nom.sql`, une transaction
  chacune, historique dans `schema_version`.
- Scanner : exclusions de la section 8 centralisées dans `ScanConfig`, liens symboliques
  non suivis, aucune lecture de contenu.
- Détection des changements pure (nouveau, modifié, touché, inchangé, supprimé), testée sans
  base ; hash SHA-256 seulement si nécessaire ; documents en erreur retentés.
- Pipeline : un document = une transaction ; erreur → statut `error`, le pipeline continue ;
  logs sans contenu, vérifiés par un test.
- Commande `second-brain index` : progression, résumé, `--verbose`, base dans
  `~/.local/share/second-brain/`.
- Test d'intégration : le deuxième passage ne fait aucune extraction, aucun hash, aucune écriture.
- 138 tests.

**Appris**
- L'entonnoir mtime/taille → hash → extraction : chaque étage évite le suivant.
- Transactions : tout ou rien, et un seul fsync par document au lieu d'un par ligne.
- `ON DELETE CASCADE` ne marche qu'avec `PRAGMA foreign_keys = ON`, à chaque connexion,
  et ne couvre pas les tables virtuelles (FTS5, sqlite-vec).
- `ON CONFLICT DO UPDATE` garde l'id ; `INSERT OR REPLACE` le change.
- `dirnames[:] = ...` pour piloter `os.walk` ; `lstat` pour repérer un lien sans le suivre.
- Un espion qui enveloppe un extracteur prouve qu'aucun travail n'est refait :
  compter les « inchangés » ne suffit pas.

**Difficile**
- Deux pièges silencieux de `sqlite3` : PRAGMA ignoré dans une transaction, et DDL non
  annulé dans le mode par défaut de Python. Découverts en testant avant de concevoir.
- Typer 0.27 n'utilise plus Click : il a fallu un `Protocol` plutôt qu'un type privé.

**Chiffres**
- Fixtures : 2 documents ajoutés au 1er passage, 2 inchangés au 2e, 0 relecture de fichier.
  Pas encore d'évaluation de recherche (étape 4).

## 2026-10-20 — Étape 3 : recherche lexicale BM25 (FTS5)

**Fait**
- Migration 002 : `chunks_fts` en FTS5 *external content*, triggers INSERT/DELETE/UPDATE,
  `rebuild` pour les bases existantes ; cohérence vérifiée par `integrity-check`.
- Interface `Retriever`, modèle `SearchResult`, `LexicalRetriever` (score = −bm25, extraits
  `snippet()` surlignés).
- Prétraitement des requêtes : minuscules, mots vides FR/EN, mots entre guillemets, OU.
- Commande `second-brain search` : rang, score, extrait coloré, temps de réponse.
- 192 tests.

**Appris**
- Index inversé, TF-IDF, BM25 : `k1` règle la saturation du TF, `b` la pénalité de longueur.
- FTS5 rend bm25 négatif pour qu'un ORDER BY croissant mette les meilleurs en premier.
- Sur un petit corpus, l'IDF de FTS5 devient négatif (ramené à ~0) pour un mot présent dans
  plus de la moitié des documents : les tests ont besoin de documents de remplissage.
- External content : supprimer de l'index exige l'ANCIEN texte exact ; une erreur corrompt
  l'index sans message, seul `integrity-check` la révèle.
- `unicode61 remove_diacritics 2` ignore accents et casse mais ne racinise pas :
  « registre » ne trouve pas « registres ». `porter` racinise à l'anglaise (porte → port).

**Difficile**
- Passer de ET à OU : sans ça, aucune question en langage naturel ne trouvait rien.
- Un « un document = un chunk » fausse BM25 : les longs documents sont fortement pénalisés.

**Échecs de BM25 (tâche 3.6, sur `samples/pdf`)**
12 questions, top 5 : rang 1 = 6/12, top 5 = 8/12, MRR ≈ 0,57 (ordre de grandeur).

| Cause | Questions | Exemple | Piste |
|---|---|---|---|
| Synonyme / reformulation | 2 (1 absente, 1 au rang 3) | « copies informatiques des vieux dossiers communaux » → rapport sur la « numérisation des archives municipales » : absent | vectoriel (étape 6) |
| Autre langue | 1 (rang 2, par chance) | « hybrid search evaluation recall » trouvé grâce à evaluation = évaluation | embeddings multilingues |
| Variante morphologique | 1 (absente) | « registre délibération » vs « registres de délibérations » | préfixe ou vectoriel, à mesurer |
| Extraction : césure | 1 (absente) | « provenance » stocké « pro-\nvenance » | recoller les césures, à évaluer |
| Extraction : scan | 1 (absente) | courrier scanné : aucune couche de texte | OCR, hors V0 |

BM25 réussit toutes les questions qui reprennent les mots du document et échoue dès que le
vocabulaire change. Deux échecs viennent de l'extraction, pas du classement.

## 2026-10-22 — Étape 5 : chunking (taille provisoire)

**Fait**
- `StructuredChunker` : sections Markdown (chemin des titres) ou pages PDF, puis paragraphes
  → phrases → lignes → mots, regroupés jusqu'à 400 tokens avec 50 de chevauchement.
  Chaque chunk est un extrait exact du texte (positions, pas de texte recomposé).
- Tokens comptés approximativement (mots × 1,5) derrière l'interface `TokenCounter`.
- Préfixe « titre > section » optionnel : colonne `chunks.context`, 2e colonne FTS5,
  jamais affiché (migration 003).
- Signature du découpage par document (`chunker_id`, migration 004) : changer les réglages
  redécoupe automatiquement.
- Résultats de recherche regroupés par document ; commande `chunks <fichier>`.
- 246 tests.
- **Reportées** : 5.5 (mesure 200 / 400 / 800, avec et sans préfixe) et 5.6 (ADR),
  faute d'évaluation (étape 4 reportée).

**Appris**
- Découper sert BM25 (pénalité de longueur), les embeddings (un vecteur = une idée) et la
  limite d'entrée des modèles (~512 tokens, le reste est tronqué en silence).
- Un token n'est pas un mot : ~1,3 à 1,5 token par mot en français.
- Le chevauchement coûte cher : 100 sur 400 → 13 chunks au lieu de 10 (+30 %).
- Deux colonnes FTS5 permettent d'indexer un texte sans l'afficher.
- Une donnée dérivée (chunks, plus tard vecteurs) doit porter la signature de ce qui l'a
  produite, sinon elle reste périmée quand les réglages changent.

**Difficile**
- Des tests sur du texte « propre » passaient alors qu'un vrai PDF donnait un chunk
  commençant par « gée cette année » : dans un PDF, chaque ligne visuelle finit par `\n`,
  donc les phrases doivent passer avant les lignes.
- L'intégration a révélé deux manques : les bases existantes n'étaient pas redécoupées, et
  la recherche affichait trois fois le même document.

**Chiffres**
- Corpus `samples/pdf` : 5 → 19 chunks. « recherche hybride » : écart slides / article
  passé de 1,05 / 0,62 à 2,87 / 2,77 (la pénalité de longueur a presque disparu).
  Pas de mesure Recall/MRR : l'évaluation n'existe pas encore.

## 2026-11-04 — Étape 6 : embeddings et recherche vectorielle

**Fait**
- Interface `Embedder` et `FastEmbedEmbedder` (fastembed, ONNX) : préfixes et
  normalisation gérés par nous, lots, chargement paresseux du modèle.
- `model_id` = nom + signature des préfixes : changer de modèle ou de préfixes recalcule
  les vecteurs concernés, et seulement eux.
- sqlite-vec chargé à chaque connexion ; `chunk_vectors` en table ordinaire (migration
  005), purge en cascade, recherche en force brute.
- Indexation en deux phases : le texte par document (tout ou rien), puis les vecteurs
  manquants par lots. Une interruption est reprise au passage suivant.
- `search --mode semantic`. Modèle par défaut : embeddinggemma-300m (ADR 0009).
- 303 tests (+ 1 avec un vrai modèle, `-m model`).

**Appris**
- Un embedding est un point dans un espace où la proximité = le sens ; vecteurs
  normalisés → cosinus = produit scalaire.
- fastembed n'ajoute ni les préfixes ni toujours la normalisation : oublier `query: `
  dégrade e5 en silence, sans aucune erreur.
- Les vecteurs sont un index dérivé : mieux vaut « manquant » (visible, réparable) que
  « faux » (invisible).
- Le plus gros modèle n'est pas le meilleur : e5-large (560 M) finit dernier sur nos deux
  jeux, derrière embeddinggemma (300 M) et même potion sur `samples`.
- Le jeu de questions décide du gagnant : sur EDiTh (codes, noms propres) BM25 gagne ;
  sur `samples` (synonymes, langue, césure) le sémantique gagne. D'où l'hybride.

**Difficile**
- Les tests de la CLI chargeaient le vrai modèle sans le dire (35 s, téléchargement en
  CI) : il a fallu un point d'injection (`_make_embedder`).
- L'archive EDiTh contenait 263 fichiers macOS `._*.pdf` à exclure.
- 13 h 44 d'horloge pour 1 h 55 de calcul : la machine s'était mise en veille
  (`systemd-inhibit` ensuite). `time.perf_counter` ne compte pas la veille, `/usr/bin/time` si.

**Chiffres** (exploratoires, script hors projet, étape 4 reportée)

| | EDiTh MRR | samples MRR | Vecteurs EDiTh (6 375 chunks) | Mémoire |
|---|---|---|---|---|
| BM25 | 0,67 | 0,58 | – | – |
| potion | 0,38 | 0,72 | 15 s | 1,4 Go |
| embeddinggemma | 0,48 | 0,75 | 1 h 55 | 4,6 Go |
| e5-large | 0,28 | 0,63 | 3 h 26 | 4,7 Go |
