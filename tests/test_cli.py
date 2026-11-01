import re
from importlib.metadata import version
from pathlib import Path

import pymupdf
import pytest
from fakes import FakeEmbedder
from typer.testing import CliRunner

from second_brain import cli
from second_brain.cli import app

runner = CliRunner()
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")  # codes de style du terminal : \x1b[1m, \x1b[0m…


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    """Jamais de vrai modèle dans les tests de la CLI (ni téléchargement, ni lenteur)."""
    embedder = FakeEmbedder("faux#1")
    monkeypatch.setattr(cli, "_make_embedder", lambda config: embedder)
    return embedder


def test_version_affiche_la_version_du_paquet() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == version("second-brain")


def test_help_liste_les_commandes() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    # En CI (GITHUB_ACTIONS), Typer force les couleurs : on retire les codes ANSI.
    plain = ANSI_ESCAPE.sub("", result.stdout)
    # Espaces autour du nom : sinon « index » serait trouvé dans « indexés ».
    for command in ("index", "search", "extract", "chunks"):
        assert f" {command} " in plain


# --- extract ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_affiche_titre_pages_scan_et_apercu() -> None:
    result = runner.invoke(app, ["extract", str(FIXTURES / "comparatif-bdd.md")])

    assert result.exit_code == 0
    assert "Comparatif des bases de données" in result.stdout
    assert "Pages     : 1" in result.stdout
    assert "Scanné    : non" in result.stdout
    assert "PostgreSQL" in result.stdout


def test_extract_sans_titre(tmp_path: Path) -> None:
    result = runner.invoke(app, ["extract", str(FIXTURES / "idees.txt")])

    assert result.exit_code == 0
    assert "Titre     : (aucun)" in result.stdout


def test_extract_limite_l_apercu_a_500_caracteres(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    path.write_text("a" * 500 + "MARQUEUR_APRES_500", encoding="utf-8")

    result = runner.invoke(app, ["extract", str(path)])

    assert result.exit_code == 0
    assert "a" * 500 in result.stdout
    assert "MARQUEUR_APRES_500" not in result.stdout
    assert "500 premiers caractères sur 518" in result.stdout


def test_extract_signale_un_pdf_scanne(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path)

    result = runner.invoke(app, ["extract", str(path)])

    assert result.exit_code == 0
    assert "Scanné    : oui" in result.stdout


def test_extract_format_non_supporte(tmp_path: Path) -> None:
    path = tmp_path / "tableur.xlsx"
    path.write_bytes(b"")

    result = runner.invoke(app, ["extract", str(path)])

    assert result.exit_code == 1
    assert "Format non supporté : .xlsx" in result.stderr


def test_extract_pdf_corrompu_sans_contenu(tmp_path: Path) -> None:
    path = tmp_path / "corrompu.pdf"
    path.write_bytes(b"secret: pas un PDF")

    result = runner.invoke(app, ["extract", str(path)])

    assert result.exit_code == 1
    assert "corrompu.pdf" in result.stderr
    assert "secret" not in result.output


def test_extract_fichier_absent(tmp_path: Path) -> None:
    result = runner.invoke(app, ["extract", str(tmp_path / "absent.md")])

    assert result.exit_code == 2


# --- index -----------------------------------------------------------------------------


def make_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "notes"
    (folder / "sous").mkdir(parents=True)
    (folder / "a.md").write_text("# Titre\n\ntexte inventé", encoding="utf-8")
    (folder / "sous" / "b.txt").write_text("idées", encoding="utf-8")
    (folder / "corrompu.pdf").write_bytes(b"pas un PDF")
    (folder / "tableur.xlsx").write_bytes(b"")
    return folder


def index_args(folder: Path, db: Path) -> list[str]:
    return ["index", str(folder), "--db", str(db)]


def test_index_affiche_le_resume(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)

    result = runner.invoke(app, index_args(folder, tmp_path / "index.db"))

    assert result.exit_code == 0
    out = ANSI_ESCAPE.sub("", result.stdout)
    assert "Ajoutés     : 2" in out
    assert "Erreurs     : 1" in out
    assert "Supprimés   : 0" in out
    assert "Ignorés     : 1" in out
    assert "Durée" in out


def test_index_calcule_les_vecteurs(tmp_path: Path) -> None:
    result = runner.invoke(app, index_args(make_folder(tmp_path), tmp_path / "index.db"))

    assert result.exit_code == 0
    assert "Vecteurs    : 2 calculés en" in ANSI_ESCAPE.sub("", result.stdout)
    assert "(faux#1)" in result.stdout


def test_index_modele_en_panne(tmp_path: Path, fake_embedder: FakeEmbedder) -> None:
    fake_embedder.fail_on_call = 1

    result = runner.invoke(app, index_args(make_folder(tmp_path), tmp_path / "index.db"))

    assert result.exit_code == 1
    assert "échec du modèle faux#1 (RuntimeError)" in result.stderr
    assert "relancez `index`" in result.stderr


def test_index_deuxieme_passage_inchange(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    db = tmp_path / "index.db"
    runner.invoke(app, index_args(folder, db))
    (folder / "corrompu.pdf").unlink()

    result = runner.invoke(app, index_args(folder, db))

    out = ANSI_ESCAPE.sub("", result.stdout)
    assert "Ajoutés     : 0" in out
    assert "Inchangés   : 2" in out
    assert "Supprimés   : 1" in out


def test_index_cree_le_dossier_de_la_base(tmp_path: Path) -> None:
    db = tmp_path / "profond" / "dossier" / "index.db"

    result = runner.invoke(app, index_args(make_folder(tmp_path), db))

    assert result.exit_code == 0
    assert db.exists()


def test_index_base_choisie_par_variable_d_environnement(tmp_path: Path) -> None:
    db = tmp_path / "env.db"

    result = runner.invoke(
        app, ["index", str(make_folder(tmp_path))], env={"SECOND_BRAIN_DB": str(db)}
    )

    assert result.exit_code == 0
    assert db.exists()


def test_index_dossier_absent(tmp_path: Path) -> None:
    result = runner.invoke(app, index_args(tmp_path / "absent", tmp_path / "index.db"))

    assert result.exit_code == 2


def test_index_verbose_journalise_sans_contenu(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)

    result = runner.invoke(app, [*index_args(folder, tmp_path / "index.db"), "--verbose"])

    assert "a.md" in result.stderr
    assert "texte inventé" not in result.output


def test_index_verbose_donne_la_cause_des_erreurs(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)

    result = runner.invoke(app, [*index_args(folder, tmp_path / "index.db"), "--verbose"])

    assert "erreur=CorruptedDocumentError : PDF illisible : corrompu.pdf" in result.stderr


# --- search ----------------------------------------------------------------------------


def indexed_db(tmp_path: Path) -> Path:
    db = tmp_path / "index.db"
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "comparatif.md").write_text(
        "# Bases\n\n## PostgreSQL\n\nBase relationnelle, schéma strict.", encoding="utf-8"
    )
    for i, text in enumerate(
        ["recette de cuisine", "horaires de natation", "liste de courses", "roman policier"]
    ):
        (folder / f"divers-{i}.md").write_text(text, encoding="utf-8")
    for i in range(4):
        (folder / f"archive-{i}.txt").write_text(f"archives municipales lot {i}", encoding="utf-8")
    runner.invoke(app, ["index", str(folder), "--db", str(db)])
    return db


def test_search_affiche_rang_fichier_score_extrait_et_temps(tmp_path: Path) -> None:
    db = indexed_db(tmp_path)

    result = runner.invoke(app, ["search", "postgresql", "--db", str(db)])

    assert result.exit_code == 0
    out = result.stdout
    assert " 1. comparatif.md" in out
    assert "## PostgreSQL Base relationnelle" in out  # extrait sur une ligne
    assert "1 résultat en " in out and " ms" in out
    assert "\x02" not in out and "\x03" not in out  # marqueurs internes jamais affichés


def test_search_couleurs_dans_un_terminal(tmp_path: Path) -> None:
    db = indexed_db(tmp_path)

    result = runner.invoke(app, ["search", "postgresql", "--db", str(db)], color=True)

    assert re.search(r"\x1b\[[0-9;]*mPostgreSQL\x1b\[0m", result.stdout)


def test_search_sans_couleur_hors_terminal(tmp_path: Path) -> None:
    db = indexed_db(tmp_path)

    result = runner.invoke(app, ["search", "postgresql", "--db", str(db)])

    assert "\x1b[" not in result.stdout


def test_search_k_limite_les_resultats(tmp_path: Path) -> None:
    db = indexed_db(tmp_path)

    result = runner.invoke(app, ["search", "archives", "-k", "2", "--db", str(db)])

    assert " 2. " in result.stdout
    assert " 3. " not in result.stdout
    assert "2 résultats en " in result.stdout


def test_search_aucun_resultat(tmp_path: Path) -> None:
    db = indexed_db(tmp_path)

    result = runner.invoke(app, ["search", "kubernetes", "--db", str(db)])

    assert result.exit_code == 0
    assert "Aucun résultat" in result.stdout


def test_search_requete_piegeuse(tmp_path: Path) -> None:
    db = indexed_db(tmp_path)

    result = runner.invoke(app, ["search", 'C++ "NOT" *', "--db", str(db)])

    assert result.exit_code == 0


def test_search_base_absente_n_est_pas_creee(tmp_path: Path) -> None:
    db = tmp_path / "absente.db"

    result = runner.invoke(app, ["search", "postgresql", "--db", str(db)])

    assert result.exit_code == 1
    assert "second-brain index" in result.stderr
    assert not db.exists()


# --- chunks ----------------------------------------------------------------------------


def test_chunks_affiche_le_decoupage_d_un_fichier() -> None:
    result = runner.invoke(app, ["chunks", str(FIXTURES / "comparatif-bdd.md")])

    assert result.exit_code == 0
    out = ANSI_ESCAPE.sub("", result.stdout)
    assert "5 chunks" in out
    assert "#0" in out and "#4" in out
    assert "section : Comparatif des bases de données > MongoDB" in out
    assert "## MongoDB" in out


def test_chunks_reglages_en_option(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    path.write_text(" ".join(f"Phrase inventée numéro {i}." for i in range(200)), encoding="utf-8")

    small = runner.invoke(app, ["chunks", str(path), "--max-tokens", "50"])
    large = runner.invoke(app, ["chunks", str(path), "--max-tokens", "400"])

    def count(out: str) -> int:
        return int(re.search(r"(\d+) chunks?", ANSI_ESCAPE.sub("", out)).group(1))  # type: ignore[union-attr]

    assert count(small.stdout) > count(large.stdout) > 1


def test_chunks_affiche_le_contexte_avec_option() -> None:
    result = runner.invoke(app, ["chunks", str(FIXTURES / "comparatif-bdd.md"), "--context"])

    assert "contexte : Comparatif des bases de données > PostgreSQL" in result.stdout


def test_chunks_montre_debut_et_fin_et_tout_avec_full(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    words = ["mot"] * 100 + ["MILIEU_DU_TEXTE"] + ["mot"] * 100
    path.write_text("DÉBUT " + " ".join(words) + " FIN", encoding="utf-8")

    short = runner.invoke(app, ["chunks", str(path), "--max-tokens", "1000"])
    full = runner.invoke(app, ["chunks", str(path), "--max-tokens", "1000", "--full"])

    assert "DÉBUT" in short.stdout and "FIN" in short.stdout and "[…]" in short.stdout
    assert "MILIEU_DU_TEXTE" not in short.stdout
    assert "MILIEU_DU_TEXTE" in full.stdout


def test_chunks_pdf_scanne_sans_chunk(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(path)

    result = runner.invoke(app, ["chunks", str(path)])

    assert result.exit_code == 0
    assert "0 chunk" in result.stdout
    assert "scanné" in result.stdout


def test_chunks_format_non_supporte(tmp_path: Path) -> None:
    path = tmp_path / "a.xlsx"
    path.write_bytes(b"")

    result = runner.invoke(app, ["chunks", str(path)])

    assert result.exit_code == 1
    assert "Format non supporté" in result.stderr


def test_search_un_document_par_ligne_et_tous_les_chunks_en_option(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    folder = tmp_path / "corpus"
    folder.mkdir()
    sections = "\n\n".join(f"## Partie {i}\n\nArchives municipales, lot {i}." for i in range(6))
    (folder / "gros.md").write_text(f"# Archives\n\n{sections}", encoding="utf-8")
    (folder / "petit.md").write_text("Les archives scolaires.", encoding="utf-8")
    for i, text in enumerate(["recette", "natation", "courses", "roman", "vacances"]):
        (folder / f"divers-{i}.md").write_text(text, encoding="utf-8")
    runner.invoke(app, ["index", str(folder), "--db", str(db)])

    grouped = runner.invoke(app, ["search", "archives", "--db", str(db)]).stdout
    raw = runner.invoke(app, ["search", "archives", "--all-chunks", "--db", str(db)]).stdout

    assert grouped.count("gros.md  ") == 1
    assert "2 résultats" in grouped
    assert raw.count("gros.md  ") > 1


def test_index_compte_les_pdf_scannes_a_part(tmp_path: Path) -> None:
    folder = tmp_path / "corpus"
    folder.mkdir()
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(folder / "scan.pdf")

    out = runner.invoke(app, ["index", str(folder), "--db", str(tmp_path / "i.db")]).stdout

    assert "Ajoutés     : 1" in out
    assert "PDF scannés : 1" in out
