-- Préfixe de contexte « titre du document > section » (tâche 5.3).
--
-- Le contexte est stocké à part (chunks.context) et indexé dans une DEUXIÈME colonne FTS5 :
-- BM25 trouve un chunk par les mots de son contexte, mais snippet() ne lit que la colonne
-- `text`, donc l'extrait affiché reste le texte d'origine. Pas de texte dupliqué.
--
-- Une table FTS5 ne se modifie pas : on la supprime et on la recrée, triggers compris,
-- puis on reconstruit l'index à partir de chunks.

ALTER TABLE chunks ADD COLUMN context TEXT;

DROP TRIGGER chunks_fts_after_insert;
DROP TRIGGER chunks_fts_after_delete;
DROP TRIGGER chunks_fts_after_update;
DROP TABLE chunks_fts;

CREATE VIRTUAL TABLE chunks_fts USING fts5 (
    context,
    text,
    content = 'chunks',
    content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_fts_after_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, context, text) VALUES (new.id, new.context, new.text);
END;

CREATE TRIGGER chunks_fts_after_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, context, text)
    VALUES ('delete', old.id, old.context, old.text);
END;

CREATE TRIGGER chunks_fts_after_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, context, text)
    VALUES ('delete', old.id, old.context, old.text);
    INSERT INTO chunks_fts (rowid, context, text) VALUES (new.id, new.context, new.text);
END;

INSERT INTO chunks_fts (chunks_fts) VALUES ('rebuild');
