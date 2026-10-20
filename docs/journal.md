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
