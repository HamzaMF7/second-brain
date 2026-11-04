import sqlite3
from pathlib import Path

import pytest

from second_brain.config import SearchConfig
from second_brain.search.base import Retriever
from second_brain.search.lexical import LexicalRetriever
from second_brain.storage.db import open_database
from second_brain.storage.documents import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    save_document,
)

OPEN, CLOSE = SearchConfig().highlight_open, SearchConfig().highlight_close

# Des documents sans rapport avec les requêtes : sur 3 documents seulement, l'IDF de FTS5
# devient négatif (ramené à ~0) dès qu'un mot est dans plus de la moitié des documents.
FILLER = [
    "recette de la tarte aux pommes et à la cannelle",
    "horaires du club de natation pour la saison",
    "liste des courses pour la semaine prochaine",
    "notes de lecture sur un roman policier",
    "planning des vacances scolaires en famille",
]


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    conn = open_database(tmp_path / "a.db")
    for i, text in enumerate(FILLER):
        add(conn, f"/notes/divers-{i}.md", text)
    return conn


def add(conn: sqlite3.Connection, path: str, text: str) -> int:
    record = DocumentRecord(Path(path), len(text), 1_000, "h", DocumentStatus.INDEXED)
    return save_document(conn, record, [ChunkRecord(0, text)])


def search(conn: sqlite3.Connection, query: str, k: int = 10) -> list[str]:
    return [r.path.name for r in LexicalRetriever(conn).search(query, k)]


def test_le_retriever_lexical_respecte_le_contrat() -> None:
    assert issubclass(LexicalRetriever, Retriever)
    with pytest.raises(TypeError):
        Retriever()  # type: ignore[abstract]


def test_renvoie_les_chunks_correspondants_avec_leurs_identifiants(
    conn: sqlite3.Connection,
) -> None:
    document_id = add(conn, "/notes/bdd.md", "comparatif entre PostgreSQL et MongoDB")

    (result,) = LexicalRetriever(conn).search("postgresql", 10)

    assert result.path == Path("/notes/bdd.md")
    assert result.document_id == document_id
    assert conn.execute(
        "SELECT document_id FROM chunks WHERE id = ?", (result.chunk_id,)
    ).fetchone() == (document_id,)
    assert (result.page, result.section) == (None, None)


def test_aucun_resultat(conn: sqlite3.Connection) -> None:
    assert search(conn, "kubernetes") == []


def test_scores_positifs_et_decroissants_le_meilleur_en_premier(
    conn: sqlite3.Connection,
) -> None:
    add(conn, "/notes/une-fois.md", "postgresql est une base relationnelle open source")
    add(conn, "/notes/trois-fois.md", "postgresql postgresql postgresql base relationnelle")

    results = LexicalRetriever(conn).search("postgresql", 10)

    assert [r.path.name for r in results] == ["trois-fois.md", "une-fois.md"]
    assert all(r.score > 0 for r in results)
    assert results[0].score > results[1].score


def test_rang_lexical_renseigne(conn: sqlite3.Connection) -> None:
    for i in range(3):
        add(conn, f"/notes/archive-{i}.md", f"archives municipales lot {i}")

    results = LexicalRetriever(conn).search("archives", 10)

    assert [r.lexical_rank for r in results] == [1, 2, 3]
    assert all(r.semantic_rank is None for r in results)


def test_k_limite_le_nombre_de_resultats(conn: sqlite3.Connection) -> None:
    for i in range(5):
        add(conn, f"/notes/archive-{i}.md", f"archives municipales lot {i}")

    assert len(search(conn, "archives", k=3)) == 3
    assert search(conn, "archives", k=0) == []


def test_accents_et_casse_ignores(conn: sqlite3.Connection) -> None:
    add(conn, "/notes/ecole.md", "L'élève prépare son exposé à l'école")

    assert search(conn, "ELEVE ecole") == ["ecole.md"]


def test_l_extrait_surligne_les_termes_trouves(conn: sqlite3.Connection) -> None:
    long_text = " ".join(["contexte"] * 100 + ["PostgreSQL"] + ["suite"] * 100)
    add(conn, "/notes/long.md", long_text)

    (result,) = LexicalRetriever(conn).search("postgresql", 10)

    assert f"{OPEN}PostgreSQL{CLOSE}" in result.snippet  # casse d'origine conservée
    assert len(result.snippet.split()) <= SearchConfig().snippet_tokens + 2  # + « … »


@pytest.mark.parametrize(
    "query",
    ["C++", "API-472", '"', "NOT", "postgresql AND OR", "*", "l'élève", "(", "col:val", "^"],
)
def test_les_requetes_piegeuses_ne_levent_pas_d_erreur(
    conn: sqlite3.Connection, query: str
) -> None:
    LexicalRetriever(conn).search(query, 10)  # pas d'OperationalError FTS5


@pytest.mark.parametrize("query", ["", "   ", "?!", "++"])
def test_requete_sans_mot_ne_renvoie_rien(conn: sqlite3.Connection, query: str) -> None:
    assert search(conn, query) == []


def test_api_472_retrouve_le_ticket(conn: sqlite3.Connection) -> None:
    add(conn, "/notes/ticket.md", "Le ticket API-472 concerne la pagination")

    assert search(conn, "API-472") == ["ticket.md"]


def test_une_question_en_langage_naturel_trouve_le_document(conn: sqlite3.Connection) -> None:
    add(conn, "/notes/bdd.md", "Comparatif : PostgreSQL contre MongoDB pour le projet")
    add(conn, "/notes/autre.md", "PostgreSQL : sauvegarde et restauration")

    results = search(conn, "Retrouve le document où j'avais comparé PostgreSQL et MongoDB")

    assert results[0] == "bdd.md"  # contient deux termes de la requête sur trois
    assert "autre.md" in results  # en OU, un seul terme suffit pour être trouvé
