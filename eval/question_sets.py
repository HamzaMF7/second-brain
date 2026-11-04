"""Jeux de questions d'évaluation : YAML du projet et benchmark EDiTh (Véracier Industries).

Les attendus sont des chemins RELATIFS à la racine du jeu (`QuestionSet.root`).
"""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

QUESTION_TYPES = ("exact", "reformulation", "question", "multilingue")

# EDiTh ne donne pas la langue des questions : relevée à la main (tâche 6.7). Les autres
# sont en français.
EDITH_LANGUAGES = {
    q: "en" for q in ("CEO-01", "CEO-02", "FIN-03", "UK-01", "UK-02", "US-01", "US-02")
}
EDITH_LANGUAGES |= {"GMBH-01": "de", "GMBH-02": "de"}
# Classements EDiTh qui ne sont PAS des réponses : documents pièges ou hors sujet.
EDITH_NEGATIVE = frozenset({"NOT_RELEVANT", "NOISE"})


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    question: str
    type: str  # projet : un de QUESTION_TYPES ; EDiTh : langue de la question (fr, en, de)
    expected: frozenset[str]


@dataclass(frozen=True, slots=True)
class QuestionSet:
    name: str
    root: Path
    questions: list[Question]


def load_yaml(path: Path) -> QuestionSet:
    """`root` (relatif au fichier) et `questions` : id, question, type, expected."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = [_parse_question(item) for item in data["questions"]]
    ids = [q.id for q in questions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"identifiants en double : {', '.join(duplicates)}")
    return QuestionSet(path.stem, path.parent / data["root"], questions)


def _parse_question(item: dict[str, Any]) -> Question:
    qid = str(item.get("id"))
    for field in ("id", "question", "type", "expected"):
        if field not in item:
            raise ValueError(f"question {qid} : champ « {field} » manquant")
    if item["type"] not in QUESTION_TYPES:
        raise ValueError(f"question {qid} : type inconnu « {item['type']} »")
    if not item["expected"]:
        raise ValueError(f"question {qid} : aucun document attendu")
    return Question(qid, str(item["question"]), item["type"], frozenset(item["expected"]))


def load_edith(root: Path) -> QuestionSet:
    """Questions de ANSWER_KEY.json ; attendus = lignes de MASTER_INDEX.csv non négatives.

    Les questions sans aucun attendu sont ignorées (impossibles à évaluer).
    """
    key: dict[str, dict[str, Any]] = json.loads((root / "ANSWER_KEY.json").read_text("utf-8"))
    expected: dict[str, set[str]] = {qid: set() for qid in key}
    with (root / "MASTER_INDEX.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            qid = row["question_id"]
            if qid in expected and row["classification"] not in EDITH_NEGATIVE:
                expected[qid].add(f"{row['entity']}/{row['filename']}")
    questions = [
        Question(qid, case["question"], EDITH_LANGUAGES.get(qid, "fr"), frozenset(expected[qid]))
        for qid, case in key.items()
        if expected[qid]
    ]
    return QuestionSet("edith", root / "by_entity", questions)
