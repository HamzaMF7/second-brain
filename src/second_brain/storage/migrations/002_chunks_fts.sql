-- Index plein texte BM25 sur chunks.text (CLAUDE.md, sections 6 et 7).
--
-- external content (content = 'chunks') : FTS5 ne stocke que l'index inversé et relit
-- le texte dans chunks quand il en a besoin (snippet, highlight). Il ne voit donc pas
-- les modifications de chunks : les triggers ci-dessous le tiennent à jour.
--
-- Pour retirer une ligne de l'index, FTS5 doit recevoir l'ANCIEN texte exact (commande
-- 'delete' avec old.text) : c'est ainsi qu'il sait quels mots décrémenter. Un texte
-- différent corromprait l'index sans erreur.
--
-- Les BEGIN ... END ci-dessous délimitent le corps des triggers, pas une transaction.

CREATE VIRTUAL TABLE chunks_fts USING fts5 (
    text,
    content = 'chunks',
    content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_fts_after_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER chunks_fts_after_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER chunks_fts_after_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;

-- Base déjà remplie avant cette migration : indexer les chunks existants.
INSERT INTO chunks_fts (chunks_fts) VALUES ('rebuild');
