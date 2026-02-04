"""Suggerimenti contestuali per tipo pagina."""

from typing import List, Dict

SUGGESTIONS: Dict[str, List[str]] = {
    "default": [
        "Come sei arrivato qui?",
        "Cosa cercheresti su Google per trovare questo posto?",
        "Prenoteresti? Perche'?",
        "Cosa manca?",
        "A chi mostreresti questo sito?",
        "Torneresti a controllare questo sito?",
        "Che funzione vorresti trovare?",
        "Confronta con dove vai di solito",
    ],
    "homepage": [
        "Prima impressione?",
        "Cosa ti ha colpito per primo?",
        "Capisci subito di cosa si tratta?",
        "Ti viene voglia di esplorare?",
        "Come sei arrivato qui?",
        "Cosa cercheresti su Google?",
    ],
    "menu": [
        "I prezzi ti sembrano giusti per te?",
        "Cosa ordineresti?",
        "Manca qualcosa che cercavi?",
        "Il menu e' chiaro?",
        "Ti fidi della qualita'?",
        "Come confronti con altri posti?",
    ],
    "booking": [
        "E' facile prenotare?",
        "Che info ti mancano per decidere?",
        "Cosa ti frena dal prenotare ora?",
        "Ti fidi a lasciare i tuoi dati?",
        "Prenoteresti o chiameresti?",
    ],
    "about": [
        "Ti fidi di piu' dopo aver letto?",
        "Cosa ti ha convinto o lasciato dubbi?",
        "Era quello che cercavi?",
        "Manca qualcosa che vorresti sapere?",
    ],
    "gallery": [
        "Le foto ti convincono?",
        "Cosa ti trasmettono?",
        "Manca qualcosa che vorresti vedere?",
        "Ti aiutano a decidere?",
    ],
    "contact": [
        "Trovi facilmente come raggiungerli?",
        "Li contatteresti? Come?",
        "Manca qualche info?",
    ],
    "other": [
        "Cosa stai cercando?",
        "Questa pagina ti e' utile?",
        "Cosa faresti ora?",
    ]
}


def get_suggestions(page_type: str) -> List[str]:
    """
    Restituisce i suggerimenti per un tipo di pagina.

    Args:
        page_type: Tipo di pagina (homepage, menu, booking, etc.)

    Returns:
        Lista di suggerimenti contestuali
    """
    return SUGGESTIONS.get(page_type, SUGGESTIONS["default"])


def get_all_suggestions() -> List[str]:
    """
    Restituisce tutti i suggerimenti unici disponibili.

    Returns:
        Lista di tutti i suggerimenti senza duplicati
    """
    all_suggestions = set()
    for suggestions in SUGGESTIONS.values():
        all_suggestions.update(suggestions)
    return list(all_suggestions)
