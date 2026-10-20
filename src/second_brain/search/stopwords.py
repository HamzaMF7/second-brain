"""Mots vides français et anglais retirés des requêtes.

Listes volontairement courtes : articles, pronoms, prépositions, conjonctions, formes
courantes d'être / avoir / faire, mots interrogatifs. Les mots ambigus qui portent souvent
du sens sont exclus (« été » la saison, « contre », « pas », « point »…).
« c » n'y est pas : le tokenizer réduit « C++ » à « c ».
La comparaison ignore accents et casse (voir query.normalize_word).
"""


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


FRENCH = _words(
    """
    a ai aie aient aies ait as au aux avaient avais avait avez aviez avions avoir avons
    ayant ce ceci cela celle celles celui ces cet cette ceux chez comme comment d dans
    de des du elle elles en es est et eu eux faire fais fait font il ils j je l la le
    les leur leurs lui m ma mais me mes moi mon même n ne nos notre nous on ont ou où
    par pour qu quand que quel quelle quelles quels qui quoi s sa sans se ses si son
    sont sous suis sur t ta te tes toi ton tu un une vos votre vous y à étaient étais
    était étiez étions êtes être
    """
)

ENGLISH = _words(
    """
    a about an and any are as at be been being but by can could did do does doing for
    from had has have having he her hers him his how i if in into is it its me my no nor
    not of on or our ours she so than that the their them then there these they this
    those to too us was we were what when where which while who whom why will with would
    you your yours
    """
)
