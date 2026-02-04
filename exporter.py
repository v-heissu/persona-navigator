"""Export sessione in formato Markdown."""

from datetime import datetime
from typing import Dict, List, Any

from personas import get_persona


def export_session(
    url: str,
    persona_id: str,
    mode: str,
    objective: str,
    history: List[Dict[str, Any]]
) -> str:
    """
    Esporta la sessione in formato Markdown.

    Args:
        url: URL del sito navigato
        persona_id: ID della persona
        mode: Modalita' (guided/autonomous)
        objective: Obiettivo (solo per autonomous)
        history: Cronologia della sessione

    Returns:
        Stringa Markdown della sessione
    """
    persona = get_persona(persona_id)
    persona_name = persona.name if persona else persona_id

    mode_label = "Guidata" if mode == "guided" else "Autonoma"

    md = f"""# Sessione Personas Navigator

**Data:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Sito:** {url}
**Persona:** {persona_name}
**Modalita':** {mode_label}
"""

    if mode == "autonomous" and objective:
        md += f"**Obiettivo:** {objective}\n"

    md += """
---

## Percorso di navigazione

"""

    current_page = None

    for entry in history:
        entry_type = entry.get("type", "")

        if entry_type == "navigation":
            page_type = entry.get("page_type", "other")
            page_url = entry.get("url", "")
            timestamp = entry.get("timestamp", "")

            md += f"""
### {page_type.title()}
**URL:** {page_url}
**Timestamp:** {timestamp}

"""
            current_page = page_type

        elif entry_type == "comment":
            content = entry.get("content", "")
            md += f"""**Commento:**
> {content}

"""

        elif entry_type == "action":
            action = entry.get("action", {})
            action_type = action.get("type", "")
            target = action.get("target", "")
            reasoning = entry.get("reasoning", "")

            action_str = f"{action_type}"
            if target:
                action_str += f" -> {target}"

            md += f"""**Azione:** {action_str}
"""
            if reasoning:
                md += f"""**Motivazione:** {reasoning}

"""

        elif entry_type == "question":
            content = entry.get("content", "")
            md += f"""**Domanda:** {content}

"""

        elif entry_type == "answer":
            content = entry.get("content", "")
            md += f"""**Risposta:**
> {content}

"""

    md += """
---

## Note e insight

_[Spazio per appunti del facilitatore]_

"""

    return md


def format_history_entry(
    entry_type: str,
    timestamp: str,
    page_type: str = None,
    url: str = None,
    content: str = None,
    action: Dict[str, str] = None,
    reasoning: str = None,
    screenshot_b64: str = None
) -> Dict[str, Any]:
    """
    Formatta un entry per la cronologia.

    Args:
        entry_type: Tipo di entry (navigation, comment, question, answer, action)
        timestamp: Timestamp dell'entry
        page_type: Tipo di pagina (per navigation)
        url: URL (per navigation)
        content: Contenuto testuale
        action: Dizionario azione (per action)
        reasoning: Motivazione (per action)
        screenshot_b64: Screenshot in base64

    Returns:
        Dizionario formattato per la cronologia
    """
    entry = {
        "type": entry_type,
        "timestamp": timestamp
    }

    if page_type:
        entry["page_type"] = page_type

    if url:
        entry["url"] = url

    if content:
        entry["content"] = content

    if action:
        entry["action"] = action

    if reasoning:
        entry["reasoning"] = reasoning

    if screenshot_b64:
        entry["screenshot_b64"] = screenshot_b64

    return entry


def get_current_timestamp() -> str:
    """Restituisce il timestamp corrente formattato."""
    return datetime.now().strftime("%H:%M:%S")
