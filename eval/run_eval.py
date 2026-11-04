"""Évalue les modes de recherche sur un jeu de questions et sauvegarde le résultat.

    uv run python eval/run_eval.py --set samples --db datasets/samples.db
    uv run python eval/run_eval.py --set edith --db datasets/veracier-gemma.db --rrf-k 20 60 100 \
        --weights 1,1 2,1 1,2 --fusion chunk document

Les attendus non indexables (PDF scannés, erreurs) sont retirés avant le calcul : aucune
méthode de recherche ne peut les trouver. Une question sans attendu indexable est ignorée.
Chaque exécution est écrite dans eval/results/ avec sa configuration complète.
"""

import argparse
import itertools
import json
import sqlite3
import statistics
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

from metrics import hit_at_k, recall_at_k, reciprocal_rank
from question_sets import Question, QuestionSet, load_edith, load_yaml

from second_brain.config import ChunkingConfig, EmbeddingConfig, SearchConfig
from second_brain.embeddings.base import Embedder
from second_brain.embeddings.fastembed_embedder import FastEmbedEmbedder
from second_brain.search.base import Retriever
from second_brain.search.grouping import search_documents
from second_brain.search.hybrid import HybridRetriever
from second_brain.search.lexical import LexicalRetriever
from second_brain.search.semantic import SemanticRetriever
from second_brain.storage.db import open_database
from second_brain.storage.documents import DocumentStatus, documents_under
from second_brain.storage.vectors import chunks_needing_vectors

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_DIR.parent
K = 10  # documents demandés par question ; MRR calculé sur ces K
METRICS: dict[str, Callable[[list[str], frozenset[str]], float]] = {
    "Hit@1": lambda r, e: hit_at_k(r, e, 1),
    "Hit@5": lambda r, e: hit_at_k(r, e, 5),
    "R@5": lambda r, e: recall_at_k(r, e, 5),
    "R@10": lambda r, e: recall_at_k(r, e, 10),
    "MRR": lambda r, e: reciprocal_rank(r, e, K),
}


@dataclass
class Run:
    """Une configuration de recherche évaluée sur toutes les questions."""

    label: str
    config: SearchConfig
    mode: str
    per_question: dict[str, dict[str, float]] = field(default_factory=dict)


def load_set(name: str) -> QuestionSet:
    if name == "samples":
        return replace(load_yaml(EVAL_DIR / "questions.yaml"), name="samples")
    return load_edith(PROJECT_ROOT / "datasets" / "veracier")


def indexable(qset: QuestionSet, conn: sqlite3.Connection) -> tuple[list[Question], dict[str, int]]:
    """Questions réduites à leurs attendus indexés, et ce qui a été retiré."""
    root = qset.root.resolve()
    status = {str(d.path.relative_to(root)): d.status for d in documents_under(conn, root)}
    kept: list[Question] = []
    removed = {"attendus non indexables": 0, "questions sans attendu indexable": 0}
    for q in qset.questions:
        ok = frozenset(p for p in q.expected if status.get(p) is DocumentStatus.INDEXED)
        removed["attendus non indexables"] += len(q.expected) - len(ok)
        if ok:
            kept.append(Question(q.id, q.question, q.type, ok))
        else:
            removed["questions sans attendu indexable"] += 1
    if not status:
        sys.exit(f"Aucun document de {root} dans la base : lance d'abord `second-brain index`.")
    return kept, removed


def make_retriever(run: Run, conn: sqlite3.Connection, embedder: Embedder | None) -> Retriever:
    lexical = LexicalRetriever(conn, run.config)
    if run.mode == "lexical":
        return lexical
    assert embedder is not None
    semantic = SemanticRetriever(conn, embedder, run.config)
    if run.mode == "semantic":
        return semantic
    return HybridRetriever(lexical, semantic, run.config)


def evaluate(run: Run, retriever: Retriever, questions: list[Question], root: Path) -> None:
    for q in questions:
        results = search_documents(retriever, q.question, K, run.config.fetch_factor)
        ranked = [str(r.path.relative_to(root)) for r in results if r.path.is_relative_to(root)]
        run.per_question[q.id] = {name: f(ranked, q.expected) for name, f in METRICS.items()}


def mean_table(
    runs: list[Run], questions: list[Question], title: str, group: Callable[[Question], str]
) -> tuple[str, dict[str, dict[str, dict[str, float]]]]:
    """Tableau Markdown des moyennes par (groupe, run), et les mêmes chiffres en dict."""
    groups = sorted({group(q) for q in questions})
    lines = [f"### {title}", "", "| groupe | n | méthode | " + " | ".join(METRICS) + " |"]
    lines.append("|---|---|---|" + "---|" * len(METRICS))
    data: dict[str, dict[str, dict[str, float]]] = {}
    for g in groups:
        ids = [q.id for q in questions if group(q) == g]
        for run in runs:
            means = {m: statistics.mean(run.per_question[i][m] for i in ids) for m in METRICS}
            data.setdefault(g, {})[run.label] = means
            cells = " | ".join(f"{v:.2f}" for v in means.values())
            lines.append(f"| {g} | {len(ids)} | {run.label} | {cells} |")
    return "\n".join(lines), data


def parse_weights(text: str) -> tuple[float, float]:
    lexical, semantic = (float(x) for x in text.split(","))
    return lexical, semantic


def git_commit() -> str:
    out = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "describe", "--always", "--dirty"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or "inconnu"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=["samples", "edith"], required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["lexical", "semantic", "hybrid"],
        choices=["lexical", "semantic", "hybrid"],
    )
    parser.add_argument("--rrf-k", nargs="+", type=int, default=[SearchConfig().rrf_k])
    parser.add_argument(
        "--weights",
        nargs="+",
        type=parse_weights,
        default=[SearchConfig().rrf_weights],
        help="poids lexical,sémantique (ex. 2,1)",
    )
    parser.add_argument(
        "--fusion", nargs="+", choices=["chunk", "document"], default=[SearchConfig().fusion]
    )
    args = parser.parse_args()
    if not args.db.is_file():
        sys.exit(f"Base introuvable : {args.db}")

    qset = load_set(args.set)
    root = qset.root.resolve()
    conn = open_database(args.db)
    questions, removed = indexable(qset, conn)

    runs: list[Run] = []
    for mode in args.modes:
        if mode == "hybrid":
            for k, weights, fusion in itertools.product(args.rrf_k, args.weights, args.fusion):
                config = SearchConfig(rrf_k=k, rrf_weights=weights, fusion=fusion)
                label = f"hybrid k={k} w={weights[0]:g},{weights[1]:g} {fusion}"
                runs.append(Run(label, config, mode))
        else:
            runs.append(Run(mode, SearchConfig(), mode))

    embedder: Embedder | None = None
    if any(run.mode != "lexical" for run in runs):
        embedder = FastEmbedEmbedder(EmbeddingConfig())
        missing = len(chunks_needing_vectors(conn, embedder.model_id))
        if missing:
            print(f"Attention : {missing} chunk(s) sans vecteur pour {embedder.model_id}.")

    for run in runs:
        evaluate(run, make_retriever(run, conn, embedder), questions, root)
        print(f"{run.label} : fait", file=sys.stderr)

    by_all, data_all = mean_table(runs, questions, "Global", lambda q: "tous")
    by_type, data_type = mean_table(
        runs, questions, "Par type" if args.set == "samples" else "Par langue", lambda q: q.type
    )
    print(f"\n{qset.name} : {len(questions)} questions évaluées ; retirés : {removed}\n")
    print(by_all, "\n", by_type, sep="\n")

    now = datetime.now()
    record = {
        "date": now.isoformat(timespec="seconds"),
        "set": qset.name,
        "db": str(args.db),
        "git": git_commit(),
        "k": K,
        "removed": removed,
        "embedding": {
            "model_id": embedder.model_id if embedder else None,
            "batch_size": EmbeddingConfig().batch_size,  # pas cache_dir : chemin personnel
        },
        "chunking": asdict(ChunkingConfig()),
        "runs": {run.label: {"mode": run.mode, "search": asdict(run.config)} for run in runs},
        "global": data_all["tous"],
        "by_type": data_type,
        "per_question": {run.label: run.per_question for run in runs},
    }
    out = EVAL_DIR / "results" / f"{now:%Y-%m-%d_%H%M}_{qset.name}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultat enregistré : {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
