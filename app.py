"""Personas Navigator - Main Streamlit Application."""

import time
import streamlit as st
from datetime import datetime

from personas import get_all_personas, get_persona, get_system_prompt, OBJECTIVES
from suggestions import get_suggestions
from browser import BrowserManager
from claude_client import ClaudeClient
from page_detector import detect_page_type, get_page_label
from navigator import NavigationState, execute_navigation_command
from exporter import export_session, format_history_entry, get_current_timestamp


# Configurazione pagina
st.set_page_config(
    page_title="Personas Navigator",
    page_icon=":performing_arts:",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizzato
st.markdown("""
<style>
    .persona-comment {
        background-color: #f0f2f6;
        border-left: 4px solid #667eea;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 8px 8px 0;
    }
    .action-box {
        background-color: #e8f4f8;
        border-left: 4px solid #17a2b8;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Inizializza lo stato della sessione."""
    defaults = {
        # Setup
        "persona_id": "marco",
        "url": "",
        "mode": "guided",
        "objective": "evaluate_booking",
        "max_steps": 5,

        # Stato navigazione
        "is_running": False,
        "navigation_state": None,

        # Contenuto corrente
        "current_screenshot_b64": None,
        "current_page_type": "other",
        "current_url": "",

        # Cronologia
        "history": [],
        "conversation_messages": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_claude_client():
    """Ottiene o crea il client Claude."""
    try:
        return ClaudeClient()
    except ValueError as e:
        st.error(f"Errore configurazione API: {e}")
        return None


def run_with_browser(func, *args, **kwargs):
    """Esegue una funzione con un browser fresh."""
    browser = BrowserManager()
    try:
        browser.start()
        return func(browser, *args, **kwargs)
    finally:
        try:
            browser.stop()
        except Exception:
            pass


def do_initial_navigation(browser, url, claude, persona_id):
    """Esegue la navigazione iniziale."""
    screenshot, final_url = browser.navigate(url)
    page_type = detect_page_type(screenshot, claude)

    # Ottieni commento
    persona = get_persona(persona_id)
    system_prompt = get_system_prompt(persona)

    comment = claude.chat(
        system_prompt=system_prompt,
        user_message=f"Guarda questo screenshot della pagina web. Questa e' la {get_page_label(page_type)}. Qual e' la tua prima impressione? (2-3 frasi)",
        image_base64=screenshot
    )

    return {
        "screenshot": screenshot,
        "url": final_url,
        "page_type": page_type,
        "comment": comment
    }


def do_navigation_command(browser, current_url, command, page_type, claude, persona_id, conversation_messages):
    """Esegue un comando di navigazione."""
    # Prima naviga all'URL corrente
    browser.navigate(current_url)

    # Poi esegui il comando
    result = execute_navigation_command(
        browser=browser,
        command=command,
        current_url=current_url,
        page_type=page_type,
        claude_client=claude
    )

    # Ottieni commento
    persona = get_persona(persona_id)
    system_prompt = get_system_prompt(persona)

    comment = claude.chat(
        system_prompt=system_prompt,
        user_message=f"Sei appena arrivato su questa pagina ({get_page_label(result.get('page_type', 'other'))}). Cosa ne pensi? (2-3 frasi)",
        conversation_history=conversation_messages,
        image_base64=result.get("screenshot")
    )

    result["comment"] = comment
    return result


def do_question(claude, question, persona_id, conversation_messages, screenshot):
    """Risponde a una domanda."""
    persona = get_persona(persona_id)
    system_prompt = get_system_prompt(persona)

    return claude.chat(
        system_prompt=system_prompt,
        user_message=question,
        conversation_history=conversation_messages,
        image_base64=screenshot
    )


def start_navigation():
    """Avvia la navigazione iniziale."""
    claude = get_claude_client()
    if not claude:
        return

    url = st.session_state.url

    with st.spinner("Caricamento pagina..."):
        try:
            result = run_with_browser(
                do_initial_navigation,
                url,
                claude,
                st.session_state.persona_id
            )

            # Aggiorna stato
            st.session_state.current_screenshot_b64 = result["screenshot"]
            st.session_state.current_page_type = result["page_type"]
            st.session_state.current_url = result["url"]
            st.session_state.is_running = True

            # Inizializza navigation state
            st.session_state.navigation_state = NavigationState(
                max_steps=st.session_state.max_steps
            )
            st.session_state.navigation_state.record_visit(result["url"], result["page_type"])

            # Aggiungi alla cronologia
            st.session_state.history.append(format_history_entry(
                entry_type="navigation",
                timestamp=get_current_timestamp(),
                page_type=result["page_type"],
                url=result["url"],
                screenshot_b64=result["screenshot"]
            ))

            st.session_state.history.append(format_history_entry(
                entry_type="comment",
                timestamp=get_current_timestamp(),
                content=result["comment"]
            ))

            st.session_state.conversation_messages.append({
                "role": "assistant",
                "content": result["comment"]
            })

        except Exception as e:
            st.error(f"Errore durante la navigazione: {e}")


def handle_user_input(user_input: str):
    """Gestisce l'input dell'utente."""
    claude = get_claude_client()
    if not claude:
        return

    # Classifica input
    input_type, content = claude.classify_input(user_input)

    if input_type == "NAVIGATE":
        with st.spinner("Navigazione in corso..."):
            try:
                result = run_with_browser(
                    do_navigation_command,
                    st.session_state.current_url,
                    content,
                    st.session_state.current_page_type,
                    claude,
                    st.session_state.persona_id,
                    st.session_state.conversation_messages
                )

                # Aggiorna stato
                st.session_state.current_screenshot_b64 = result.get("screenshot", "")
                st.session_state.current_page_type = result.get("page_type", "other")
                st.session_state.current_url = result.get("url", "")

                # Aggiungi alla cronologia
                st.session_state.history.append(format_history_entry(
                    entry_type="navigation",
                    timestamp=get_current_timestamp(),
                    page_type=result.get("page_type"),
                    url=result.get("url"),
                    screenshot_b64=result.get("screenshot")
                ))

                st.session_state.history.append(format_history_entry(
                    entry_type="comment",
                    timestamp=get_current_timestamp(),
                    content=result.get("comment", "")
                ))

                st.session_state.conversation_messages.append({
                    "role": "assistant",
                    "content": result.get("comment", "")
                })

            except Exception as e:
                st.error(f"Errore navigazione: {e}")

    else:
        # E' una domanda
        st.session_state.history.append(format_history_entry(
            entry_type="question",
            timestamp=get_current_timestamp(),
            content=user_input
        ))

        with st.spinner("Pensando..."):
            answer = do_question(
                claude,
                user_input,
                st.session_state.persona_id,
                st.session_state.conversation_messages,
                st.session_state.current_screenshot_b64
            )

        st.session_state.history.append(format_history_entry(
            entry_type="answer",
            timestamp=get_current_timestamp(),
            content=answer
        ))

        st.session_state.conversation_messages.append({
            "role": "user",
            "content": user_input
        })
        st.session_state.conversation_messages.append({
            "role": "assistant",
            "content": answer
        })


def reset_session():
    """Resetta la sessione."""
    st.session_state.navigation_state = None
    st.session_state.is_running = False
    st.session_state.current_screenshot_b64 = None
    st.session_state.current_page_type = "other"
    st.session_state.current_url = ""
    st.session_state.history = []
    st.session_state.conversation_messages = []


def render_setup_form():
    """Renderizza il form di setup."""
    st.markdown("### Setup")

    # Selezione persona
    personas = get_all_personas()
    persona_options = {p.name: p.id for p in personas}

    selected_name = st.selectbox(
        "Persona",
        options=list(persona_options.keys()),
        index=0
    )
    st.session_state.persona_id = persona_options[selected_name]

    # Mostra descrizione persona
    persona = get_persona(st.session_state.persona_id)
    if persona:
        st.caption(persona.short_description)

    # URL
    st.session_state.url = st.text_input(
        "URL sito",
        value=st.session_state.url,
        placeholder="https://esempio.com"
    )

    # Pulsante avvia
    if st.button("Avvia navigazione", type="primary", use_container_width=True):
        if not st.session_state.url:
            st.error("Inserisci un URL")
        else:
            start_navigation()
            st.rerun()


def render_screenshot():
    """Renderizza lo screenshot corrente."""
    if st.session_state.current_screenshot_b64:
        st.image(
            f"data:image/png;base64,{st.session_state.current_screenshot_b64}",
            use_column_width=True
        )


def render_page_info():
    """Renderizza informazioni sulla pagina corrente."""
    page_type = st.session_state.current_page_type
    label = get_page_label(page_type)

    st.markdown(f"**Pagina:** {label}")
    st.caption(st.session_state.current_url)


def render_latest_comment():
    """Renderizza l'ultimo commento della persona."""
    for entry in reversed(st.session_state.history):
        if entry.get("type") == "comment":
            persona = get_persona(st.session_state.persona_id)
            name = persona.name.split(" - ")[0] if persona else "Persona"

            st.markdown(f"""
<div class="persona-comment">
    <strong>{name}:</strong><br>
    "{entry.get('content', '')}"
</div>
""", unsafe_allow_html=True)
            break


def render_input_section():
    """Renderizza la sezione di input."""
    persona = get_persona(st.session_state.persona_id)
    name = persona.name.split(" - ")[0] if persona else "la persona"

    # Form input
    with st.form(key="user_input_form", clear_on_submit=True):
        user_input = st.text_input(
            f"Chiedi a {name}:",
            placeholder="Scrivi un comando (vai al menu) o una domanda (prenoteresti?)"
        )

        submitted = st.form_submit_button("Invia", use_container_width=True)

        if submitted and user_input:
            handle_user_input(user_input)
            st.rerun()

    # Suggerimenti
    st.markdown("**Suggerimenti:**")
    suggestions = get_suggestions(st.session_state.current_page_type)

    cols = st.columns(3)
    for i, suggestion in enumerate(suggestions[:6]):
        with cols[i % 3]:
            if st.button(suggestion, key=f"sugg_{i}", use_container_width=True):
                handle_user_input(suggestion)
                st.rerun()


def render_history():
    """Renderizza la cronologia della sessione."""
    st.markdown("### Cronologia")

    if not st.session_state.history:
        st.caption("Nessuna attivita' ancora")
        return

    for entry in st.session_state.history:
        entry_type = entry.get("type", "")
        timestamp = entry.get("timestamp", "")

        if entry_type == "navigation":
            page_type = entry.get("page_type", "other")
            st.markdown(f"**{timestamp}** | {get_page_label(page_type)}")

        elif entry_type == "comment":
            content = entry.get("content", "")[:100]
            st.markdown(f"> \"{content}{'...' if len(entry.get('content', '')) > 100 else ''}\"")

        elif entry_type == "question":
            st.markdown(f"**Domanda:** {entry.get('content', '')}")

        elif entry_type == "answer":
            content = entry.get("content", "")[:100]
            st.markdown(f"> {content}{'...' if len(entry.get('content', '')) > 100 else ''}")

        st.markdown("---")


def render_export_section():
    """Renderizza la sezione di export."""
    col1, col2 = st.columns(2)

    with col1:
        md_content = export_session(
            url=st.session_state.url,
            persona_id=st.session_state.persona_id,
            mode=st.session_state.mode,
            objective=st.session_state.get("objective", ""),
            history=st.session_state.history
        )

        st.download_button(
            label="Esporta MD",
            data=md_content,
            file_name=f"sessione_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True
        )

    with col2:
        if st.button("Nuova sessione", use_container_width=True):
            reset_session()
            st.rerun()


def main():
    """Main application."""
    init_session_state()

    st.markdown("# Personas Navigator")

    if not st.session_state.is_running:
        render_setup_form()
    else:
        col_main, col_side = st.columns([2, 1])

        with col_main:
            render_screenshot()
            render_page_info()
            render_latest_comment()
            st.markdown("---")
            render_input_section()

        with col_side:
            render_history()
            st.markdown("---")
            render_export_section()


if __name__ == "__main__":
    main()
