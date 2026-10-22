from pathlib import Path

import pytest

from second_brain.chunking.base import Chunker
from second_brain.chunking.models import Chunk
from second_brain.chunking.structured import StructuredChunker, split_sentences
from second_brain.chunking.tokens import TokenCounter, WordTokenCounter
from second_brain.config import ChunkingConfig
from second_brain.extraction.markdown import MarkdownExtractor, parse_headings
from second_brain.extraction.models import ExtractedDocument, Page

FIXTURES = Path(__file__).parent.parent / "fixtures"


def chunker(max_tokens: int = 400, overlap: int = 0) -> StructuredChunker:
    return StructuredChunker(ChunkingConfig(max_tokens=max_tokens, overlap_tokens=overlap))


def pdf_like(*pages: str) -> ExtractedDocument:
    pages_ = tuple(Page(number=i, text=text) for i, text in enumerate(pages, start=1))
    return ExtractedDocument(path=Path("rapport.pdf"), title=None, pages=pages_)


def sentences(count: int, words_each: int = 8) -> str:
    """Texte inventé de `count` phrases distinctes."""
    return " ".join(" ".join(f"mot{i}x{j}" for j in range(words_each)) + "." for i in range(count))


def assert_exact_extracts(doc: ExtractedDocument, chunks: list[Chunk]) -> None:
    for chunk in chunks:
        assert doc.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text


# --- Compteur de tokens -------------------------------------------------------------------


def test_word_token_counter_est_prudent() -> None:
    counter = WordTokenCounter(tokens_per_word=1.5)

    assert counter.count("un deux trois") == 5  # 3 mots × 1,5 = 4,5 → arrondi au-dessus
    assert counter.count("   ") == 0


def test_les_compteurs_respectent_le_contrat() -> None:
    assert issubclass(WordTokenCounter, TokenCounter)
    assert issubclass(StructuredChunker, Chunker)
    with pytest.raises(TypeError):
        Chunker()  # type: ignore[abstract]


# --- Markdown : découpage par section ------------------------------------------------------


def test_markdown_un_chunk_par_section_avec_le_chemin_des_titres() -> None:
    doc = MarkdownExtractor().extract(FIXTURES / "comparatif-bdd.md")

    chunks = chunker().chunk(doc)

    title = "Comparatif des bases de données"
    assert [c.section for c in chunks] == [
        title,
        f"{title} > PostgreSQL",
        f"{title} > PostgreSQL > Extensions utiles",
        f"{title} > MongoDB",
        f"{title} > Conclusion",
    ]
    assert chunks[1].text.startswith("## PostgreSQL")
    assert all(c.page is None for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert_exact_extracts(doc, chunks)


def markdown(text: str) -> ExtractedDocument:
    return ExtractedDocument(Path("a.md"), None, (Page(1, text),), parse_headings(text))


def test_texte_avant_le_premier_titre_sans_section() -> None:
    doc = markdown("Introduction libre.\n\n# Partie\n\nContenu.")

    chunks = chunker().chunk(doc)

    assert [(c.section, c.text) for c in chunks] == [
        (None, "Introduction libre."),
        ("Partie", "# Partie\n\nContenu."),
    ]


def test_une_section_trop_longue_est_redecoupee_sans_deborder_sur_la_suivante() -> None:
    doc = markdown(f"# Longue\n\n{sentences(30)}\n\n# Courte\n\nfin.")

    chunks = chunker(max_tokens=60, overlap=15).chunk(doc)

    assert {c.section for c in chunks} == {"Longue", "Courte"}
    assert sum(c.section == "Longue" for c in chunks) > 1
    assert chunks[-1].text == "# Courte\n\nfin."  # pas de chevauchement venu de « Longue »
    assert_exact_extracts(doc, chunks)


# --- PDF : la page est une frontière stricte ----------------------------------------------


def test_pdf_un_chunk_par_page_et_jamais_a_cheval() -> None:
    doc = pdf_like("Texte de la page un.", "Texte de la page deux.", "Page trois.")

    chunks = chunker().chunk(doc)

    assert [(c.page, c.text) for c in chunks] == [
        (1, "Texte de la page un."),
        (2, "Texte de la page deux."),
        (3, "Page trois."),
    ]
    assert all(c.section is None for c in chunks)
    assert_exact_extracts(doc, chunks)  # positions qui tiennent compte des séparateurs


def test_pages_vides_ignorees() -> None:
    doc = pdf_like("Contenu.", "   \n  ", "Suite.")

    assert [c.page for c in chunker().chunk(doc)] == [1, 3]


def test_page_longue_redecoupee_en_restant_sur_sa_page() -> None:
    doc = pdf_like(sentences(40), "Petite page.")

    chunks = chunker(max_tokens=80, overlap=0).chunk(doc)

    assert sum(c.page == 1 for c in chunks) > 1
    assert chunks[-1].page == 2
    assert_exact_extracts(doc, chunks)


# --- Taille, chevauchement, couverture -----------------------------------------------------


def test_aucun_chunk_ne_depasse_la_taille_maximale() -> None:
    doc = pdf_like(f"{sentences(25)}\n\n{sentences(25)}\n{sentences(10, words_each=20)}")

    chunks = chunker(max_tokens=50, overlap=10).chunk(doc)

    assert chunks
    assert all(c.token_count <= 50 for c in chunks)


def test_token_count_est_celui_du_compteur() -> None:
    doc = pdf_like(sentences(20))
    counter = WordTokenCounter()

    for chunk in chunker(max_tokens=50).chunk(doc):
        assert chunk.token_count == counter.count(chunk.text)


def test_sans_chevauchement_les_chunks_couvrent_tout_le_texte_une_seule_fois() -> None:
    doc = pdf_like(sentences(30), sentences(12))

    chunks = chunker(max_tokens=40, overlap=0).chunk(doc)

    assert " ".join(c.text for c in chunks).split() == doc.text.split()


def test_avec_chevauchement_deux_chunks_voisins_partagent_du_texte() -> None:
    doc = pdf_like(sentences(30))

    chunks = chunker(max_tokens=40, overlap=15).chunk(doc)

    assert len(chunks) > 2
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start < previous.start + len(previous.text)  # recouvrement
        assert current.start > previous.start  # mais on avance toujours


def test_un_mot_plus_long_que_la_taille_maximale_ne_boucle_pas() -> None:
    doc = pdf_like("a" * 5000)

    chunks = chunker(max_tokens=1).chunk(doc)

    assert [c.text for c in chunks] == ["a" * 5000]


def test_document_vide() -> None:
    assert chunker().chunk(pdf_like("")) == []


# --- Phrases -------------------------------------------------------------------------------


def test_split_sentences_coupe_apres_la_ponctuation_finale() -> None:
    assert split_sentences("Première phrase. Deuxième ? Troisième ! Fin…") == [
        "Première phrase. ",
        "Deuxième ? ",
        "Troisième ! ",
        "Fin…",
    ]


def test_split_sentences_ne_coupe_pas_les_abreviations() -> None:
    text = "M. Dupont a vu le Dr. Martin, etc. et p. ex. J. Durand. Fin."

    assert split_sentences(text) == [
        "M. Dupont a vu le Dr. Martin, etc. et p. ex. J. Durand. ",
        "Fin.",
    ]


def test_split_sentences_ne_coupe_pas_les_nombres() -> None:
    assert split_sentences("Le taux est de 3.5 % cette année. Fin.") == [
        "Le taux est de 3.5 % cette année. ",
        "Fin.",
    ]


def test_split_sentences_avec_guillemets_francais() -> None:
    assert split_sentences("Il a dit « oui. » Puis il est parti.") == [
        "Il a dit « oui. » ",
        "Puis il est parti.",
    ]


def test_un_pdf_est_coupe_entre_deux_phrases_pas_en_fin_de_ligne() -> None:
    # Texte de PDF : un « \n » à chaque ligne visuelle, phrases à cheval sur les lignes.
    page = "\n".join(
        f"Phrase {i} qui commence sur une ligne et se termine sur la" + f"\nsuivante {i}."
        for i in range(30)
    )

    chunks = chunker(max_tokens=60, overlap=0).chunk(pdf_like(page))

    assert len(chunks) > 1
    assert all(c.text.startswith("Phrase") for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)


# --- Préfixe de contexte (tâche 5.3) -------------------------------------------------------


def with_prefix(max_tokens: int = 400) -> StructuredChunker:
    return StructuredChunker(ChunkingConfig(max_tokens=max_tokens, context_prefix=True))


def test_sans_option_aucun_contexte() -> None:
    doc = MarkdownExtractor().extract(FIXTURES / "comparatif-bdd.md")

    assert all(c.context is None for c in chunker().chunk(doc))


def test_contexte_titre_et_section_sans_repeter_le_titre() -> None:
    doc = MarkdownExtractor().extract(FIXTURES / "comparatif-bdd.md")

    chunks = with_prefix().chunk(doc)

    title = "Comparatif des bases de données"
    assert [c.context for c in chunks] == [
        title,
        f"{title} > PostgreSQL",
        f"{title} > PostgreSQL > Extensions utiles",
        f"{title} > MongoDB",
        f"{title} > Conclusion",
    ]


def test_le_texte_du_chunk_reste_l_extrait_d_origine() -> None:
    doc = MarkdownExtractor().extract(FIXTURES / "comparatif-bdd.md")

    chunks = with_prefix().chunk(doc)

    assert [c.text for c in chunks] == [c.text for c in chunker().chunk(doc)]
    assert_exact_extracts(doc, chunks)


def test_contexte_d_une_page_pdf_est_le_titre() -> None:
    doc = ExtractedDocument(Path("a.pdf"), "Rapport annuel 2025", (Page(1, "Texte."),))

    (chunk,) = with_prefix().chunk(doc)

    assert chunk.context == "Rapport annuel 2025"


def test_sans_titre_le_nom_du_fichier_sert_de_titre() -> None:
    doc = ExtractedDocument(Path("/notes/rapport_final_v2.pdf"), None, (Page(1, "Texte."),))

    (chunk,) = with_prefix().chunk(doc)

    assert chunk.context == "rapport_final_v2"


def test_section_differente_du_titre_est_ajoutee_au_titre() -> None:
    doc = ExtractedDocument(
        Path("notes.md"),
        "Mes notes",
        (Page(1, "## Partie\n\nTexte."),),
        parse_headings("## Partie\n\nTexte."),
    )

    (chunk,) = with_prefix().chunk(doc)

    assert chunk.context == "Mes notes > Partie"


# --- Signature du découpage ----------------------------------------------------------------


def test_la_signature_change_avec_chaque_reglage() -> None:
    ids = {
        StructuredChunker(ChunkingConfig()).id,
        StructuredChunker(ChunkingConfig(max_tokens=200)).id,
        StructuredChunker(ChunkingConfig(overlap_tokens=0)).id,
        StructuredChunker(ChunkingConfig(context_prefix=True)).id,
        StructuredChunker(ChunkingConfig(tokens_per_word=1.3)).id,
    }

    assert len(ids) == 5


def test_la_signature_est_stable() -> None:
    assert StructuredChunker().id == StructuredChunker().id
    assert StructuredChunker().id == "structured:max400:overlap50:ctx0:words×1.5"
