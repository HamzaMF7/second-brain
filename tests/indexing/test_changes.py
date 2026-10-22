import hashlib
from pathlib import Path

from second_brain.indexing.changes import KnownChange, KnownDocument, detect_changes, sha256_file
from second_brain.indexing.scanner import ScannedFile

ROOT = Path("/notes")


class FakeHasher:
    """Faux hasheur : renvoie un hash fixé par chemin et compte ses appels."""

    def __init__(self, hashes: dict[str, str] | None = None) -> None:
        self.hashes = hashes or {}
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> str:
        self.calls.append(path)
        if path.name not in self.hashes:
            raise PermissionError(path.name)  # fichier devenu illisible
        return self.hashes[path.name]


def scanned(name: str, size: int = 100, mtime_ns: int = 1_000) -> ScannedFile:
    return ScannedFile(path=ROOT / name, size=size, mtime_ns=mtime_ns)


def known(
    name: str,
    *,
    id: int = 1,
    size: int = 100,
    mtime_ns: int = 1_000,
    content_hash: str | None = "h-ancien",
    had_error: bool = False,
) -> KnownDocument:
    return KnownDocument(
        id=id,
        path=ROOT / name,
        size=size,
        mtime_ns=mtime_ns,
        content_hash=content_hash,
        had_error=had_error,
    )


# --- Les 5 cas -----------------------------------------------------------------------------


def test_nouveau_fichier_sans_calcul_de_hash() -> None:
    hasher = FakeHasher()

    changes = detect_changes([scanned("a.md")], [], hasher)

    assert changes.new == [scanned("a.md")]
    assert hasher.calls == []  # le pipeline calculera le hash en indexant


def test_inchange_quand_mtime_et_taille_identiques_sans_calcul_de_hash() -> None:
    hasher = FakeHasher()
    document = known("a.md")

    changes = detect_changes([scanned("a.md")], [document], hasher)

    assert changes.unchanged == [document]
    assert hasher.calls == []  # tout l'intérêt de l'entonnoir


def test_inchange_quand_mtime_change_mais_hash_identique() -> None:
    hasher = FakeHasher({"a.md": "h-ancien"})
    file = scanned("a.md", mtime_ns=2_000)  # `touch a.md`

    changes = detect_changes([file], [known("a.md", id=7)], hasher)

    assert changes.touched == [KnownChange(file=file, document_id=7, content_hash="h-ancien")]
    assert changes.modified == []
    assert hasher.calls == [file.path]


def test_modifie_quand_mtime_change_et_hash_different() -> None:
    hasher = FakeHasher({"a.md": "h-nouveau"})
    file = scanned("a.md", mtime_ns=2_000)

    changes = detect_changes([file], [known("a.md", id=7)], hasher)

    assert changes.modified == [KnownChange(file=file, document_id=7, content_hash="h-nouveau")]


def test_supprime_quand_le_fichier_n_est_plus_sur_le_disque() -> None:
    document = known("disparu.md")

    changes = detect_changes([], [document], FakeHasher())

    assert changes.deleted == [document]


# --- Cas limites ---------------------------------------------------------------------------


def test_taille_differente_suffit_a_conclure_modifie_sans_hash() -> None:
    hasher = FakeHasher()
    file = scanned("a.md", size=150, mtime_ns=2_000)

    changes = detect_changes([file], [known("a.md", id=7)], hasher)

    assert changes.modified == [KnownChange(file=file, document_id=7, content_hash=None)]
    assert hasher.calls == []  # tailles différentes = contenus différents, inutile de lire


def test_fichier_devenu_illisible_est_a_retraiter() -> None:
    file = scanned("a.md", mtime_ns=2_000)

    changes = detect_changes([file], [known("a.md", id=7)], FakeHasher())

    # Le pipeline tentera l'extraction et enregistrera l'erreur.
    assert changes.modified == [KnownChange(file=file, document_id=7, content_hash=None)]


def test_document_en_erreur_est_retente_meme_si_rien_n_a_change() -> None:
    # Ex. : droits de lecture rétablis (chmod ne change pas le mtime).
    hasher = FakeHasher()
    file = scanned("a.pdf")

    changes = detect_changes([file], [known("a.pdf", id=7, had_error=True)], hasher)

    assert changes.modified == [KnownChange(file=file, document_id=7, content_hash=None)]
    assert changes.unchanged == []
    assert hasher.calls == []


def test_chaque_fichier_tombe_dans_exactement_une_categorie() -> None:
    hasher = FakeHasher({"touche.md": "h-ancien", "modifie.md": "h-nouveau"})
    files = [
        scanned("nouveau.md"),
        scanned("inchange.md"),
        scanned("touche.md", mtime_ns=2_000),
        scanned("modifie.md", mtime_ns=2_000),
    ]
    documents = [
        known("inchange.md", id=1),
        known("touche.md", id=2),
        known("modifie.md", id=3),
        known("supprime.md", id=4),
    ]

    changes = detect_changes(files, documents, hasher)

    assert [f.path.name for f in changes.new] == ["nouveau.md"]
    assert [d.id for d in changes.unchanged] == [1]
    assert [c.document_id for c in changes.touched] == [2]
    assert [c.document_id for c in changes.modified] == [3]
    assert [d.id for d in changes.deleted] == [4]


def test_aucun_changement_sur_deux_listes_vides() -> None:
    changes = detect_changes([], [], FakeHasher())

    assert (changes.new, changes.modified, changes.touched) == ([], [], [])
    assert (changes.unchanged, changes.deleted) == ([], [])


# --- Hash réel -----------------------------------------------------------------------------


def test_sha256_file_hash_connu(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"abc")

    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_file_lit_les_gros_fichiers_par_blocs(tmp_path: Path) -> None:
    # Plus grand qu'un bloc de lecture : le résultat doit être celui du fichier entier.
    path = tmp_path / "gros.bin"
    path.write_bytes(b"x" * 3_000_000)

    assert sha256_file(path) == hashlib.sha256(b"x" * 3_000_000).hexdigest()


# --- Signature du découpage ----------------------------------------------------------------


def test_decoupage_different_rend_le_document_modifie_sans_hash() -> None:
    hasher = FakeHasher()
    file = scanned("a.md")
    document = KnownDocument(
        id=7,
        path=file.path,
        size=100,
        mtime_ns=1_000,
        content_hash="h",
        had_error=False,
        chunker_id="structured:max400",
    )

    changes = detect_changes([file], [document], hasher, chunker_id="structured:max200")

    assert changes.modified == [KnownChange(file=file, document_id=7, content_hash=None)]
    assert hasher.calls == []


def test_meme_decoupage_inchange() -> None:
    file = scanned("a.md")
    document = KnownDocument(
        id=7,
        path=file.path,
        size=100,
        mtime_ns=1_000,
        content_hash="h",
        had_error=False,
        chunker_id="structured:max400",
    )

    changes = detect_changes([file], [document], FakeHasher(), chunker_id="structured:max400")

    assert changes.unchanged == [document]


def test_document_sans_signature_est_redecoupe() -> None:
    # Base remplie avant la migration 004 : chunker_id inconnu (NULL).
    file = scanned("a.md")
    document = known("a.md", id=7)

    changes = detect_changes([file], [document], FakeHasher(), chunker_id="structured:max400")

    assert [c.document_id for c in changes.modified] == [7]
