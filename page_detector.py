"""Rilevamento tipo pagina tramite Claude Vision."""

from typing import Optional
from claude_client import ClaudeClient


# Tipi di pagina supportati
PAGE_TYPES = [
    "homepage",
    "menu",
    "booking",
    "about",
    "gallery",
    "contact",
    "other"
]

# Prompt per il rilevamento
DETECTION_PROMPT = """Analizza questo screenshot di un sito web e determina il tipo di pagina.

Rispondi SOLO con una di queste categorie:
- homepage
- menu
- booking
- about
- gallery
- contact
- other

Una sola parola."""


def detect_page_type(
    screenshot_base64: str,
    claude_client: Optional[ClaudeClient] = None
) -> str:
    """
    Rileva il tipo di pagina dallo screenshot.

    Args:
        screenshot_base64: Screenshot in base64
        claude_client: Client Claude (opzionale, ne crea uno se non fornito)

    Returns:
        Tipo di pagina (homepage, menu, booking, about, gallery, contact, other)
    """
    if not claude_client:
        claude_client = ClaudeClient()

    response = claude_client.analyze_image(
        image_base64=screenshot_base64,
        system_prompt="Sei un analizzatore di pagine web. Rispondi con una sola parola.",
        user_prompt=DETECTION_PROMPT
    )

    # Normalizza la risposta
    page_type = response.strip().lower()

    # Verifica che sia un tipo valido
    if page_type in PAGE_TYPES:
        return page_type

    # Prova a estrarre un tipo valido dalla risposta
    for pt in PAGE_TYPES:
        if pt in page_type:
            return pt

    return "other"


def get_page_emoji(page_type: str) -> str:
    """
    Restituisce l'emoji per un tipo di pagina.

    Args:
        page_type: Tipo di pagina

    Returns:
        Emoji corrispondente
    """
    emojis = {
        "homepage": "home",
        "menu": "fork_and_knife",
        "booking": "calendar",
        "about": "information_source",
        "gallery": "camera",
        "contact": "telephone_receiver",
        "other": "page_facing_up"
    }
    return emojis.get(page_type, "page_facing_up")


def get_page_label(page_type: str) -> str:
    """
    Restituisce l'etichetta italiana per un tipo di pagina.

    Args:
        page_type: Tipo di pagina

    Returns:
        Etichetta in italiano
    """
    labels = {
        "homepage": "Homepage",
        "menu": "Menu",
        "booking": "Prenotazione",
        "about": "Chi siamo",
        "gallery": "Galleria",
        "contact": "Contatti",
        "other": "Altra pagina"
    }
    return labels.get(page_type, "Pagina")
