-- Signature du découpage utilisé pour chaque document (comme model_id pour les vecteurs).
-- Si les réglages du chunker changent, les documents concernés sont redécoupés, même si
-- leur fichier n'a pas bougé. Les documents existants (NULL) seront tous redécoupés.

ALTER TABLE documents ADD COLUMN chunker_id TEXT;
