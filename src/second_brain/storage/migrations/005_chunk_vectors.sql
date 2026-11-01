-- Un vecteur par chunk, avec le modèle qui l'a produit (model_id = nom#signature des préfixes).
-- Table ordinaire plutôt que table virtuelle vec0 : la dimension reste libre (plusieurs
-- modèles candidats) et la purge suit le chunk par ON DELETE CASCADE. La recherche se fait
-- en force brute avec les fonctions de sqlite-vec (vec_distance_cosine).
-- Redécouper un document remplace ses chunks (nouveaux id) : ses vecteurs partent avec.

CREATE TABLE chunk_vectors (
    chunk_id  INTEGER PRIMARY KEY REFERENCES chunks (id) ON DELETE CASCADE,
    model_id  TEXT    NOT NULL,
    -- float32 little-endian, 4 octets par composante (format attendu par sqlite-vec)
    embedding BLOB    NOT NULL CHECK (length(embedding) > 0 AND length(embedding) % 4 = 0)
) STRICT;

-- Retrouver les vecteurs d'un autre modèle, à recalculer quand le modèle change.
CREATE INDEX chunk_vectors_model_id ON chunk_vectors (model_id);
