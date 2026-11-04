"""Chargement des jeux de questions : YAML du projet et benchmark EDiTh (fichiers inventés)."""

import json
from pathlib import Path

import pytest
from question_sets import EDITH_LANGUAGES, load_edith, load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def write_yaml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "questions.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_yaml_racine_relative_au_fichier(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        """
root: docs/pdf
questions:
  - id: Q1
    question: taux de reprise
    type: exact
    expected: [rapport.pdf, sous/dossier.pdf]
""",
    )

    qset = load_yaml(path)

    assert qset.name == "questions"
    assert qset.root == tmp_path / "docs/pdf"
    [q] = qset.questions
    assert (q.id, q.question, q.type) == ("Q1", "taux de reprise", "exact")
    assert q.expected == frozenset({"rapport.pdf", "sous/dossier.pdf"})


@pytest.mark.parametrize(
    ("question", "message"),
    [
        ("{id: Q1, question: q, type: magique, expected: [a.pdf]}", "type"),
        ("{id: Q1, question: q, type: exact, expected: []}", "attendu"),
        ("{id: Q1, question: q, type: exact}", "expected"),
    ],
)
def test_yaml_question_invalide(tmp_path: Path, question: str, message: str) -> None:
    path = write_yaml(tmp_path, f"root: .\nquestions:\n  - {question}\n")

    with pytest.raises(ValueError, match=message):
        load_yaml(path)


def test_yaml_identifiants_uniques(tmp_path: Path) -> None:
    q = "{id: Q1, question: q, type: exact, expected: [a.pdf]}"
    path = write_yaml(tmp_path, f"root: .\nquestions:\n  - {q}\n  - {q}\n")

    with pytest.raises(ValueError, match="Q1"):
        load_yaml(path)


def test_questions_du_projet_valides() -> None:
    qset = load_yaml(PROJECT_ROOT / "eval" / "questions.yaml")

    assert len(qset.questions) == 12
    for q in qset.questions:
        for rel in q.expected:
            assert (qset.root / rel).is_file(), f"{q.id} : {rel} absent"


def make_edith(root: Path) -> Path:
    (root / "by_entity").mkdir(parents=True)
    key = {
        "CEO-01": {"question": "Risk map of inherited contracts?"},
        "GMBH-01": {"question": "Prozess-FMEAs aktuell?"},
        "FIN-01": {"question": "Documentation prix de transfert ?"},
    }
    (root / "ANSWER_KEY.json").write_text(json.dumps(key), encoding="utf-8")
    (root / "MASTER_INDEX.csv").write_text(
        "doc_id,question_id,role,entity,filename,classification,language,format,pages,description\n"
        "D1,CEO-01,CEO,precistec,contrats/a.pdf,SANCTIONS_RISK,fr,searchable,3,x\n"
        "D2,CEO-01,CEO,precistec,contrats/bruit.pdf,NOISE,fr,searchable,3,x\n"
        "D3,CEO-01,CEO,veracier_sa,b.pdf,NOT_RELEVANT,fr,searchable,3,x\n"
        "D4,GMBH-01,QM,veracier_gmbh,fmea.pdf,CURRENT,de,searchable,3,x\n"
        "D5,FIN-01,DAF,veracier_sa,tp.pdf,REQUIRED,fr,searchable,3,x\n"
        "D6,AUTRE-01,DAF,veracier_sa,hors-cle.pdf,REQUIRED,fr,searchable,3,x\n",
        encoding="utf-8",
    )
    return root


def test_edith_attendus_sans_bruit_et_langue_comme_type(tmp_path: Path) -> None:
    qset = load_edith(make_edith(tmp_path / "veracier"))

    assert qset.name == "edith"
    assert qset.root == tmp_path / "veracier" / "by_entity"
    by_id = {q.id: q for q in qset.questions}
    assert set(by_id) == {"CEO-01", "GMBH-01", "FIN-01"}  # AUTRE-01 : absent de la clé
    assert by_id["CEO-01"].expected == frozenset({"precistec/contrats/a.pdf"})
    assert by_id["CEO-01"].question == "Risk map of inherited contracts?"
    assert [by_id[i].type for i in ("CEO-01", "GMBH-01", "FIN-01")] == ["en", "de", "fr"]


def test_edith_langues_connues() -> None:
    assert EDITH_LANGUAGES["GMBH-02"] == "de"
    assert EDITH_LANGUAGES["US-01"] == "en"
    assert "FIN-01" not in EDITH_LANGUAGES  # français par défaut
