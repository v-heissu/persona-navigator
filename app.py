"""Personas Navigator - Main Streamlit Application."""

import base64
import streamlit as st
from datetime import datetime

from personas import get_all_personas, get_persona, get_system_prompt, OBJECTIVES
from suggestions import get_suggestions
from browser import BrowserManager
from claude_client import ClaudeClient
from page_detector import detect_page_type, get_page_label, get_page_emoji
from navigator import NavigationState, AutonomousNavigator, execute_navigation_command
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
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
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
    .history-entry {
        border-bottom: 1px solid #eee;
        padding: 0.5rem 0;
    }
    .suggestion-btn {
        margin: 0.2rem;
    }
    .step-indicator {
        font-size: 0.9rem;
        color: #666;
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
        "navigation_state": None,
        "is_running": False,
        "is_paused": False,
        "is_autonomous_running": False,

        # Contenuto corrente
        "current_screenshot_b64": None,
        "current_page_type": "other",
        "current_url": "",

        # Browser e client
        "browser": None,
        "claude_client": None,
        "autonomous_navigator": None,

        # Cronologia
        "history": [],
        "conversation_messages": [],

        # UI state
        "user_input": "",
        "skip_wait": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_claude_client():
    """Ottiene o crea il client Claude."""
    if st.session_state.claude_client is None:
        try:
            st.session_state.claude_client = ClaudeClient()
        except ValueError as e:
            st.error(f"Errore configurazione API: {e}")
            return None
    return st.session_state.claude_client


def get_browser():
    """Ottiene o crea il browser manager."""
    if st.session_state.browser is None:
        st.session_state.browser = BrowserManager()
    return st.session_state.browser


def start_navigation(url: str):
    """Avvia la navigazione iniziale."""
    browser = get_browser()
    claude = get_claude_client()

    if not claude:
        return

    try:
        browser.start()
        screenshot, final_url = browser.navigate(url)

        # Rileva tipo pagina
        page_type = detect_page_type(screenshot, claude)

        # Aggiorna stato
        st.session_state.current_screenshot_b64 = screenshot
        st.session_state.current_page_type = page_type
        st.session_state.current_url = final_url
        st.session_state.is_running = True

        # Inizializza navigation state
        st.session_state.navigation_state = NavigationState(
            max_steps=st.session_state.max_steps
        )
        st.session_state.navigation_state.record_visit(final_url, page_type)

        # Aggiungi alla cronologia
        st.session_state.history.append(format_history_entry(
            entry_type="navigation",
            timestamp=get_current_timestamp(),
            page_type=page_type,
            url=final_url,
            screenshot_b64=screenshot
        ))

        # Ottieni commento iniziale dalla persona
        persona = get_persona(st.session_state.persona_id)
        system_prompt = get_system_prompt(persona)

        comment = claude.chat(
            system_prompt=system_prompt,
            user_message=f"Guarda questo screenshot della pagina web. Questa e' la {get_page_label(page_type)}. Qual e' la tua prima impressione? (2-3 frasi)",
            image_base64=screenshot
        )

        # Aggiungi commento alla cronologia
        st.session_state.history.append(format_history_entry(
            entry_type="comment",
            timestamp=get_current_timestamp(),
            content=comment
        ))

        # Aggiungi alla conversazione per context
        st.session_state.conversation_messages.append({
            "role": "assistant",
            "content": comment
        })

    except Exception as e:
        st.error(f"Errore durante la navigazione: {e}")
        st.session_state.is_running = False


def handle_autonomous_step():
    """Gestisce uno step della navigazione autonoma."""
    navigator = st.session_state.autonomous_navigator

    if not navigator or navigator.is_stopped:
        st.session_state.is_autonomous_running = False
        return

    if navigator.is_paused:
        return

    result = navigator.next_step()

    # Aggiorna stato
    st.session_state.current_screenshot_b64 = result.get("screenshot", "")
    st.session_state.current_page_type = result.get("page_type", "other")
    st.session_state.current_url = result.get("url", "")

    # Aggiungi alla cronologia
    if result.get("url"):
        st.session_state.history.append(format_history_entry(
            entry_type="navigation",
            timestamp=get_current_timestamp(),
            page_type=result.get("page_type"),
            url=result.get("url"),
            screenshot_b64=result.get("screenshot")
        ))

    if result.get("comment"):
        st.session_state.history.append(format_history_entry(
            entry_type="comment",
            timestamp=get_current_timestamp(),
            content=result.get("comment")
        ))

    if result.get("action") and result.get("action") != "DONE":
        st.session_state.history.append(format_history_entry(
            entry_type="action",
            timestamp=get_current_timestamp(),
            action={
                "type": result.get("action"),
                "target": result.get("target", "")
            },
            reasoning=result.get("reasoning", "")
        ))

    if result.get("is_done"):
        st.session_state.is_autonomous_running = False


def handle_user_input(user_input: str):
    """Gestisce l'input dell'utente in modalita' guidata."""
    claude = get_claude_client()
    browser = get_browser()

    if not claude or not browser:
        return

    persona = get_persona(st.session_state.persona_id)
    system_prompt = get_system_prompt(persona)

    # Classifica input
    input_type, content = claude.classify_input(user_input)

    if input_type == "NAVIGATE":
        # Esegui navigazione
        result = execute_navigation_command(
            browser=browser,
            command=content,
            current_url=st.session_state.current_url,
            page_type=st.session_state.current_page_type,
            claude_client=claude
        )

        # Aggiorna stato
        st.session_state.current_screenshot_b64 = result.get("screenshot", "")
        st.session_state.current_page_type = result.get("page_type", "other")
        st.session_state.current_url = result.get("url", "")

        # Aggiungi navigazione alla cronologia
        st.session_state.history.append(format_history_entry(
            entry_type="navigation",
            timestamp=get_current_timestamp(),
            page_type=result.get("page_type"),
            url=result.get("url"),
            screenshot_b64=result.get("screenshot")
        ))

        # Ottieni commento sulla nuova pagina
        comment = claude.chat(
            system_prompt=system_prompt,
            user_message=f"Sei appena arrivato su questa pagina ({get_page_label(result.get('page_type', 'other'))}). Cosa ne pensi? (2-3 frasi)",
            conversation_history=st.session_state.conversation_messages,
            image_base64=result.get("screenshot")
        )

        st.session_state.history.append(format_history_entry(
            entry_type="comment",
            timestamp=get_current_timestamp(),
            content=comment
        ))

        st.session_state.conversation_messages.append({
            "role": "assistant",
            "content": comment
        })

    else:
        # E' una domanda
        st.session_state.history.append(format_history_entry(
            entry_type="question",
            timestamp=get_current_timestamp(),
            content=user_input
        ))

        # Rispondi alla domanda
        answer = claude.chat(
            system_prompt=system_prompt,
            user_message=user_input,
            conversation_history=st.session_state.conversation_messages,
            image_base64=st.session_state.current_screenshot_b64
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


def start_autonomous_navigation():
    """Avvia la navigazione autonoma."""
    persona = get_persona(st.session_state.persona_id)
    claude = get_claude_client()
    browser = get_browser()

    if not claude:
        return

    navigator = AutonomousNavigator(
        persona=persona,
        objective_id=st.session_state.objective,
        max_steps=st.session_state.max_steps,
        claude_client=claude,
        browser=browser
    )

    st.session_state.autonomous_navigator = navigator
    st.session_state.is_autonomous_running = True

    # Avvia navigazione
    result = navigator.start(st.session_state.url)

    # Aggiorna stato
    st.session_state.current_screenshot_b64 = result.get("screenshot", "")
    st.session_state.current_page_type = result.get("page_type", "other")
    st.session_state.current_url = result.get("url", "")
    st.session_state.is_running = True

    # Aggiungi alla cronologia
    st.session_state.history.append(format_history_entry(
        entry_type="navigation",
        timestamp=get_current_timestamp(),
        page_type=result.get("page_type"),
        url=result.get("url"),
        screenshot_b64=result.get("screenshot")
    ))

    if result.get("comment"):
        st.session_state.history.append(format_history_entry(
            entry_type="comment",
            timestamp=get_current_timestamp(),
            content=result.get("comment")
        ))

    if result.get("action") and result.get("action") != "DONE":
        st.session_state.history.append(format_history_entry(
            entry_type="action",
            timestamp=get_current_timestamp(),
            action={
                "type": result.get("action"),
                "target": result.get("target", "")
            },
            reasoning=result.get("reasoning", "")
        ))

    if result.get("is_done"):
        st.session_state.is_autonomous_running = False


def reset_session():
    """Resetta la sessione."""
    # Chiudi browser se aperto
    if st.session_state.browser:
        st.session_state.browser.stop()

    # Reset stato
    st.session_state.navigation_state = None
    st.session_state.is_running = False
    st.session_state.is_paused = False
    st.session_state.is_autonomous_running = False
    st.session_state.current_screenshot_b64 = None
    st.session_state.current_page_type = "other"
    st.session_state.current_url = ""
    st.session_state.browser = None
    st.session_state.autonomous_navigator = None
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

    # Modalita'
    mode = st.radio(
        "Modalita'",
        options=["Guidata", "Autonoma"],
        horizontal=True
    )
    st.session_state.mode = "guided" if mode == "Guidata" else "autonomous"

    # Opzioni autonoma
    if st.session_state.mode == "autonomous":
        with st.expander("Opzioni navigazione autonoma", expanded=True):
            objective_options = {obj["label"]: obj["id"] for obj in OBJECTIVES}
            selected_objective = st.selectbox(
                "Obiettivo",
                options=list(objective_options.keys())
            )
            st.session_state.objective = objective_options[selected_objective]

            st.session_state.max_steps = st.slider(
                "Max pagine",
                min_value=3,
                max_value=10,
                value=5
            )

    # Pulsante avvia
    if st.button("Avvia navigazione", type="primary", use_container_width=True):
        if not st.session_state.url:
            st.error("Inserisci un URL")
        else:
            if st.session_state.mode == "autonomous":
                start_autonomous_navigation()
            else:
                start_navigation(st.session_state.url)
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

    nav_state = st.session_state.navigation_state
    step_info = ""
    if nav_state:
        step_info = f" | Step: {nav_state.current_step}/{nav_state.max_steps}"

    st.markdown(f"**Pagina:** {label}{step_info}")
    st.caption(st.session_state.current_url)


def render_latest_comment():
    """Renderizza l'ultimo commento della persona."""
    # Trova ultimo commento
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

    # Mostra azione se autonoma
    if st.session_state.mode == "autonomous":
        for entry in reversed(st.session_state.history):
            if entry.get("type") == "action":
                action = entry.get("action", {})
                action_type = action.get("type", "")
                target = action.get("target", "")
                reasoning = entry.get("reasoning", "")

                action_str = action_type
                if target:
                    action_str += f" su \"{target}\""

                st.markdown(f"""
<div class="action-box">
    <strong>Prossima azione:</strong> {action_str}<br>
    <em>"{reasoning}"</em>
</div>
""", unsafe_allow_html=True)
                break


def render_autonomous_controls():
    """Renderizza i controlli per la navigazione autonoma."""
    if st.session_state.is_autonomous_running:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.session_state.is_paused:
                if st.button("Riprendi", use_container_width=True):
                    st.session_state.is_paused = False
                    if st.session_state.autonomous_navigator:
                        st.session_state.autonomous_navigator.resume()
                    st.rerun()
            else:
                if st.button("Pausa", use_container_width=True):
                    st.session_state.is_paused = True
                    if st.session_state.autonomous_navigator:
                        st.session_state.autonomous_navigator.pause()
                    st.rerun()

        with col2:
            if st.button("Salta attesa", use_container_width=True):
                st.session_state.skip_wait = True
                handle_autonomous_step()
                st.rerun()

        with col3:
            if st.button("Stop -> Q&A", use_container_width=True):
                st.session_state.is_autonomous_running = False
                if st.session_state.autonomous_navigator:
                    st.session_state.autonomous_navigator.stop()
                st.rerun()


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

    # Mostra suggerimenti come bottoni
    cols = st.columns(3)
    for i, suggestion in enumerate(suggestions[:6]):
        with cols[i % 3]:
            if st.button(suggestion, key=f"sugg_{i}", use_container_width=True):
                handle_user_input(suggestion)
                st.rerun()


def render_history():
    """Renderizza la cronologia della sessione."""
    st.markdown("### Cronologia sessione")

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
            st.markdown(f"> \"{content}...\"" if len(entry.get("content", "")) > 100 else f"> \"{content}\"")

        elif entry_type == "action":
            action = entry.get("action", {})
            action_type = action.get("type", "")
            target = action.get("target", "")
            st.caption(f"-> {action_type}: {target}")

        elif entry_type == "question":
            content = entry.get("content", "")
            st.markdown(f"**Domanda:** {content}")

        elif entry_type == "answer":
            content = entry.get("content", "")[:100]
            st.markdown(f"> {content}..." if len(entry.get("content", "")) > 100 else f"> {content}")

        st.markdown("---")


def render_export_section():
    """Renderizza la sezione di export."""
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Esporta MD", use_container_width=True):
            md_content = export_session(
                url=st.session_state.url,
                persona_id=st.session_state.persona_id,
                mode=st.session_state.mode,
                objective=st.session_state.get("objective", ""),
                history=st.session_state.history
            )

            st.download_button(
                label="Scarica",
                data=md_content,
                file_name=f"sessione_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown"
            )

    with col2:
        if st.button("Nuova sessione", use_container_width=True):
            reset_session()
            st.rerun()


def main():
    """Main application."""
    init_session_state()

    # Header
    st.markdown("# Personas Navigator")

    if not st.session_state.is_running:
        # Mostra form setup
        render_setup_form()
    else:
        # Layout principale
        col_main, col_side = st.columns([2, 1])

        with col_main:
            # Screenshot
            render_screenshot()

            # Info pagina
            render_page_info()

            # Ultimo commento
            render_latest_comment()

            # Controlli autonoma
            if st.session_state.mode == "autonomous":
                render_autonomous_controls()

            # Input section (sempre visibile quando non in autonoma running o in pausa)
            if not st.session_state.is_autonomous_running or st.session_state.is_paused:
                st.markdown("---")
                render_input_section()

        with col_side:
            # Cronologia
            render_history()

            st.markdown("---")

            # Export e reset
            render_export_section()

    # Auto-advance per navigazione autonoma
    if st.session_state.is_autonomous_running and not st.session_state.is_paused:
        import time

        if not st.session_state.skip_wait:
            time.sleep(3)

        st.session_state.skip_wait = False
        handle_autonomous_step()
        st.rerun()


if __name__ == "__main__":
    main()
