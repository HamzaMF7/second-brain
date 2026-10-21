import pytest

from second_brain.search.query import to_fts5_query


def test_mots_en_minuscules_entre_guillemets_combines_en_ou() -> None:
    assert to_fts5_query("PostgreSQL contre MongoDB") == '"postgresql" OR "contre" OR "mongodb"'


def test_ou_parle_t_on_de_c_plus_plus() -> None:
    # où, t, on, de : mots vides ; C++ devient « c », comme dans le tokenizer.
    assert to_fts5_query("où parle-t-on de C++ ?") == '"parle" OR "c"'


def test_api_472() -> None:
    assert to_fts5_query("API-472") == '"api" OR "472"'


@pytest.mark.parametrize("query", ["", "   ", "?!", "++", "« »"])
def test_requete_sans_mot(query: str) -> None:
    assert to_fts5_query(query) is None


def test_mots_vides_francais_retires() -> None:
    assert to_fts5_query("Retrouve le document où j'avais comparé les bases") == (
        '"retrouve" OR "document" OR "comparé" OR "bases"'
    )


def test_mots_vides_anglais_retires() -> None:
    assert to_fts5_query("Where did I compare the databases?") == '"compare" OR "databases"'


def test_mots_vides_reconnus_sans_accent_ni_majuscule() -> None:
    assert to_fts5_query("OU EST le rapport") == '"rapport"'
    assert to_fts5_query("Où est le rapport") == '"rapport"'


def test_les_mots_ambigus_sont_gardes() -> None:
    # « été » (la saison) et « contre » portent du sens : ils ne sont pas des mots vides.
    assert to_fts5_query("vacances d'été") == '"vacances" OR "été"'


def test_repli_si_la_requete_n_a_que_des_mots_vides() -> None:
    assert to_fts5_query("le la les") == '"le" OR "la" OR "les"'
    assert to_fts5_query("Who is it") == '"who" OR "is" OR "it"'


def test_doublons_retires_dans_l_ordre() -> None:
    assert to_fts5_query("PostgreSQL postgresql MongoDB POSTGRESQL") == '"postgresql" OR "mongodb"'


def test_la_syntaxe_fts5_est_neutralisee() -> None:
    # NOT est un mot vide anglais ; : * " ( ) disparaissent.
    assert to_fts5_query('C++ "API-472" NOT col:val* (x)') == (
        '"c" OR "api" OR "472" OR "col" OR "val" OR "x"'
    )


def test_operateurs_seuls_traites_comme_des_mots() -> None:
    assert to_fts5_query("AND OR NOT") == '"and" OR "or" OR "not"'


def test_accents_conserves_dans_les_termes() -> None:
    # Le tokenizer FTS5 retirera lui-même les accents ; on ne modifie pas les termes.
    assert to_fts5_query("l'élève") == '"élève"'
