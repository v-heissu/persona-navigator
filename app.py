"""Personas Navigator - FastAPI Backend (fully async)."""

import json
import asyncio
import logging
import traceback
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from personas import get_all_personas, get_persona, get_system_prompt, get_insights_prompt, OBJECTIVES
from suggestions import get_suggestions
from browser import BrowserManager
from ai_client import AIClient
from page_detector import detect_page_type, get_page_label
from navigator import (
    NavigationState, AutonomousNavigator,
    execute_navigation_command
)
from exporter import export_session, format_history_entry, get_current_timestamp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Browser pool: one per WebSocket session
browser_sessions = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: cleanup browsers on shutdown."""
    yield
    for sid, browser in browser_sessions.items():
        try:
            await browser.stop()
        except Exception:
            pass
    browser_sessions.clear()


app = FastAPI(title="Personas Navigator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    """Serve la pagina principale."""
    return FileResponse("static/index.html")


@app.get("/api/personas")
async def get_personas():
    """Restituisce le personas disponibili."""
    personas = get_all_personas()
    return [
        {"id": p.id, "name": p.name, "description": p.short_description}
        for p in personas
    ]


@app.get("/api/objectives")
async def get_objectives():
    """Restituisce gli obiettivi disponibili."""
    return OBJECTIVES


@app.get("/api/suggestions/{page_type}")
async def get_page_suggestions(page_type: str):
    """Restituisce i suggerimenti per tipo pagina."""
    return get_suggestions(page_type)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket per la sessione di navigazione."""
    await websocket.accept()

    session_id = id(websocket)
    browser: Optional[BrowserManager] = None
    claude: Optional[AIClient] = None
    nav_state: Optional[NavigationState] = None
    history = []
    conversation_messages = []
    current_url = ""
    current_page_type = "other"
    current_screenshot = ""
    persona_id = "marco"
    site_context = ""

    async def send(event: str, data: dict):
        await websocket.send_json({"event": event, **data})

    try:
        claude = AIClient()

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            # === START: Avvia navigazione ===
            if action == "start":
                persona_id = msg.get("persona_id", "marco")
                url = msg.get("url", "")
                mode = msg.get("mode", "guided")
                max_steps = msg.get("max_steps", 5)
                site_context = msg.get("site_context", "")

                if not url:
                    await send("error", {"message": "URL mancante"})
                    continue

                await send("status", {"message": "Avvio browser..."})
                logger.info("Starting browser for session %s", session_id)

                # Avvia browser (async nativo, nessun run_in_executor)
                browser = BrowserManager()
                await browser.start()
                logger.info("Browser started, navigating to %s", url)

                screenshot, final_url = await browser.navigate(url)
                logger.info("Navigation complete, detecting page type...")

                page_type = await detect_page_type(screenshot, claude)
                logger.info("Page type: %s", page_type)

                current_url = final_url
                current_page_type = page_type
                current_screenshot = screenshot

                browser_sessions[session_id] = browser

                nav_state = NavigationState(max_steps=max_steps)
                nav_state.record_visit(final_url, page_type)

                # Ottieni primo commento
                persona = get_persona(persona_id)
                system_prompt = get_system_prompt(persona, site_context=site_context)

                comment = await claude.chat(
                    system_prompt=system_prompt,
                    user_message=f"Guarda questo screenshot della pagina web. Questa e' la {get_page_label(page_type)}. Qual e' la tua prima impressione? (2-3 frasi)",
                    image_base64=screenshot
                )
                logger.info("Got first comment from Claude")

                # Registra nella cronologia
                history.append(format_history_entry(
                    entry_type="navigation",
                    timestamp=get_current_timestamp(),
                    page_type=page_type,
                    url=final_url,
                    screenshot_b64=screenshot
                ))
                history.append(format_history_entry(
                    entry_type="comment",
                    timestamp=get_current_timestamp(),
                    content=comment
                ))
                conversation_messages.append({
                    "role": "assistant",
                    "content": comment
                })

                suggestions = get_suggestions(page_type)

                await send("navigation", {
                    "screenshot": screenshot,
                    "url": final_url,
                    "page_type": page_type,
                    "page_label": get_page_label(page_type),
                    "comment": comment,
                    "persona_name": persona.name.split(" - ")[0],
                    "suggestions": suggestions,
                    "step": nav_state.current_step,
                    "max_steps": nav_state.max_steps,
                    "history": history
                })

                # Se autonoma, avvia navigazione autonoma
                if mode == "autonomous":
                    objective_id = msg.get("objective", "first_impression")
                    await run_autonomous(
                        websocket, browser, claude, persona_id,
                        objective_id, nav_state, history,
                        conversation_messages, current_url,
                        current_page_type, current_screenshot,
                        max_steps, send, site_context
                    )

            # === INPUT: Comando o domanda ===
            elif action == "input":
                user_input = msg.get("text", "").strip()
                if not user_input or not browser or not claude:
                    continue

                persona = get_persona(persona_id)
                system_prompt = get_system_prompt(persona, site_context=site_context)

                await send("status", {"message": "Analizzo..."})

                # Classifica input
                input_type, content = await claude.classify_input(user_input)

                if input_type == "NAVIGATE":
                    await send("status", {"message": "Navigazione..."})

                    result = await execute_navigation_command(
                        browser=browser,
                        command=content,
                        current_url=current_url,
                        page_type=current_page_type,
                        claude_client=claude
                    )

                    nav_comment = await claude.chat(
                        system_prompt=system_prompt,
                        user_message=f"Sei appena arrivato su questa pagina ({get_page_label(result.get('page_type', 'other'))}). Cosa ne pensi? (2-3 frasi)",
                        conversation_history=conversation_messages,
                        image_base64=result.get("screenshot")
                    )

                    current_url = result.get("url", current_url)
                    current_page_type = result.get("page_type", "other")
                    current_screenshot = result.get("screenshot", "")

                    history.append(format_history_entry(
                        entry_type="navigation",
                        timestamp=get_current_timestamp(),
                        page_type=current_page_type,
                        url=current_url,
                        screenshot_b64=current_screenshot
                    ))
                    history.append(format_history_entry(
                        entry_type="comment",
                        timestamp=get_current_timestamp(),
                        content=nav_comment
                    ))
                    conversation_messages.append({
                        "role": "assistant",
                        "content": nav_comment
                    })

                    suggestions = get_suggestions(current_page_type)

                    await send("navigation", {
                        "screenshot": current_screenshot,
                        "url": current_url,
                        "page_type": current_page_type,
                        "page_label": get_page_label(current_page_type),
                        "comment": nav_comment,
                        "persona_name": persona.name.split(" - ")[0],
                        "suggestions": suggestions,
                        "history": history
                    })

                else:
                    # Domanda
                    history.append(format_history_entry(
                        entry_type="question",
                        timestamp=get_current_timestamp(),
                        content=user_input
                    ))

                    answer = await claude.chat(
                        system_prompt=system_prompt,
                        user_message=user_input,
                        conversation_history=conversation_messages,
                        image_base64=current_screenshot
                    )

                    history.append(format_history_entry(
                        entry_type="answer",
                        timestamp=get_current_timestamp(),
                        content=answer
                    ))
                    conversation_messages.append({
                        "role": "user", "content": user_input
                    })
                    conversation_messages.append({
                        "role": "assistant", "content": answer
                    })

                    await send("answer", {
                        "question": user_input,
                        "answer": answer,
                        "persona_name": persona.name.split(" - ")[0],
                        "history": history
                    })

            # === CLICK: Click diretto sullo screenshot ===
            elif action == "click":
                if not browser:
                    continue

                x = msg.get("x", 0)
                y = msg.get("y", 0)

                screenshot, new_url = await browser.click_at(int(x), int(y))
                new_page_type = await detect_page_type(screenshot, claude)

                current_url = new_url
                current_page_type = new_page_type
                current_screenshot = screenshot

                # Commento persona
                persona = get_persona(persona_id)
                system_prompt = get_system_prompt(persona, site_context=site_context)

                comment = await claude.chat(
                    system_prompt=system_prompt,
                    user_message=f"Sei appena arrivato su questa pagina ({get_page_label(new_page_type)}). Cosa ne pensi? (2-3 frasi)",
                    conversation_history=conversation_messages,
                    image_base64=screenshot
                )

                history.append(format_history_entry(
                    entry_type="navigation",
                    timestamp=get_current_timestamp(),
                    page_type=new_page_type,
                    url=new_url,
                    screenshot_b64=screenshot
                ))
                history.append(format_history_entry(
                    entry_type="comment",
                    timestamp=get_current_timestamp(),
                    content=comment
                ))
                conversation_messages.append({
                    "role": "assistant",
                    "content": comment
                })

                await send("navigation", {
                    "screenshot": screenshot,
                    "url": new_url,
                    "page_type": new_page_type,
                    "page_label": get_page_label(new_page_type),
                    "comment": comment,
                    "persona_name": persona.name.split(" - ")[0],
                    "suggestions": get_suggestions(new_page_type),
                    "history": history
                })

            # === SCROLL: Scroll diretto sullo screenshot ===
            elif action == "scroll":
                if not browser:
                    continue

                delta = msg.get("delta", 300)
                screenshot, new_url = await browser.scroll_by(int(delta))

                current_url = new_url
                current_screenshot = screenshot

                await send("screenshot_update", {
                    "screenshot": screenshot,
                    "url": new_url
                })

            # === INSIGHTS: Genera report miglioramenti ===
            elif action == "insights":
                if not claude or not conversation_messages:
                    await send("error", {"message": "Nessuna sessione attiva per generare insights"})
                    continue

                await send("status", {"message": "Genero insights..."})

                persona = get_persona(persona_id)

                # Build conversation summary from history
                summary_parts = []
                for entry in history:
                    etype = entry.get("type", "")
                    if etype == "navigation":
                        summary_parts.append(f"[Navigazione] {entry.get('page_type', '')} - {entry.get('url', '')}")
                    elif etype == "comment":
                        summary_parts.append(f"[Commento persona] {entry.get('content', '')}")
                    elif etype == "question":
                        summary_parts.append(f"[Domanda operatore] {entry.get('content', '')}")
                    elif etype == "answer":
                        summary_parts.append(f"[Risposta persona] {entry.get('content', '')}")
                    elif etype == "action":
                        act = entry.get("action", {})
                        summary_parts.append(f"[Azione] {act.get('type', '')} {act.get('target', '')} - {entry.get('reasoning', '')}")
                conversation_summary = "\n".join(summary_parts)

                insights_prompt = get_insights_prompt(
                    persona=persona,
                    site_context=site_context,
                    conversation_summary=conversation_summary
                )

                insights = await claude.chat(
                    system_prompt="Sei un UX researcher esperto. Rispondi in italiano.",
                    user_message=insights_prompt
                )

                await send("insights", {"content": insights, "persona_name": persona.name})

            # === EXPORT ===
            elif action == "export":
                md = export_session(
                    url=current_url,
                    persona_id=persona_id,
                    mode=msg.get("mode", "guided"),
                    objective=msg.get("objective", ""),
                    history=history
                )
                await send("export", {"markdown": md})

            # === STOP autonomous ===
            elif action == "stop_autonomous":
                pass  # Loop will be broken by flag

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as e:
        logger.error("Error in session %s: %s\n%s", session_id, e, traceback.format_exc())
        try:
            await send("error", {"message": str(e)})
        except Exception:
            pass
    finally:
        if browser:
            try:
                await browser.stop()
            except Exception:
                pass
        browser_sessions.pop(session_id, None)


async def run_autonomous(
    websocket, browser, claude, persona_id, objective_id,
    nav_state, history, conversation_messages,
    current_url, current_page_type, current_screenshot,
    max_steps, send, site_context=""
):
    """Esegue la navigazione autonoma."""
    from personas import get_navigation_prompt, get_objective_prompt

    persona = get_persona(persona_id)
    objective_prompt = get_objective_prompt(objective_id)

    for step in range(max_steps - 1):
        # Check for stop message (non-blocking)
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            msg = json.loads(raw)
            if msg.get("action") == "stop_autonomous":
                await send("autonomous_done", {"reason": "stopped", "history": history})
                return
            if msg.get("action") == "pause_autonomous":
                await send("status", {"message": "In pausa..."})
                # Wait for resume
                while True:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    if msg.get("action") == "resume_autonomous":
                        break
                    if msg.get("action") == "stop_autonomous":
                        await send("autonomous_done", {"reason": "stopped", "history": history})
                        return
                    if msg.get("action") == "input":
                        # Handle question during pause
                        user_input = msg.get("text", "").strip()
                        if user_input:
                            system_prompt = get_system_prompt(persona, site_context=site_context)
                            history.append(format_history_entry(
                                entry_type="question",
                                timestamp=get_current_timestamp(),
                                content=user_input
                            ))

                            answer = await claude.chat(
                                system_prompt=system_prompt,
                                user_message=user_input,
                                conversation_history=conversation_messages,
                                image_base64=current_screenshot
                            )
                            history.append(format_history_entry(
                                entry_type="answer",
                                timestamp=get_current_timestamp(),
                                content=answer
                            ))
                            conversation_messages.append({"role": "user", "content": user_input})
                            conversation_messages.append({"role": "assistant", "content": answer})
                            await send("answer", {
                                "question": user_input,
                                "answer": answer,
                                "persona_name": persona.name.split(" - ")[0],
                                "history": history
                            })
        except asyncio.TimeoutError:
            pass

        await send("status", {"message": f"Step {nav_state.current_step + 1}/{max_steps}..."})

        # Get persona action
        prompt = get_navigation_prompt(
            persona=persona,
            objective=objective_prompt,
            page_type=current_page_type,
            current_url=current_url,
            visited_pages=nav_state.visited_pages,
            current_step=nav_state.current_step,
            max_steps=nav_state.max_steps,
            site_context=site_context
        )
        response = await claude.analyze_image(
            image_base64=current_screenshot,
            system_prompt=f"Sei {persona.name.split(' - ')[0]}. Rispondi solo in JSON.",
            user_prompt=prompt
        )
        result = claude.parse_navigation_response(response)

        action = result.get("action", "DONE")
        target = result.get("target", "")
        comment = result.get("comment", "")
        reasoning = result.get("reasoning", "")

        # Execute action
        if action == "DONE":
            history.append(format_history_entry(
                entry_type="comment", timestamp=get_current_timestamp(), content=comment
            ))
            await send("autonomous_step", {
                "screenshot": current_screenshot,
                "url": current_url,
                "page_type": current_page_type,
                "page_label": get_page_label(current_page_type),
                "comment": comment,
                "action": action,
                "target": target,
                "reasoning": reasoning,
                "persona_name": persona.name.split(" - ")[0],
                "step": nav_state.current_step,
                "max_steps": max_steps,
                "suggestions": get_suggestions(current_page_type),
                "history": history
            })
            await send("autonomous_done", {"reason": "done", "history": history})
            return

        # Execute browser action
        if action == "CLICK" and target:
            success, new_screenshot, new_url = await browser.click_element(target)
            if success:
                new_page_type = await detect_page_type(new_screenshot, claude)
                nav_state.record_visit(new_url, new_page_type)
                current_screenshot = new_screenshot
                current_url = new_url
                current_page_type = new_page_type
            else:
                s, u = await browser.scroll_down()
                nav_state.record_scroll()
                current_screenshot = s
                current_url = u

        elif action == "SCROLL_DOWN":
            if nav_state.can_scroll():
                s, u = await browser.scroll_down()
                nav_state.record_scroll()
                current_screenshot = s
                current_url = u

        elif action == "BACK":
            s, u = await browser.go_back()
            current_screenshot = s
            current_url = u
            current_page_type = await detect_page_type(current_screenshot, claude)

        history.append(format_history_entry(
            entry_type="navigation", timestamp=get_current_timestamp(),
            page_type=current_page_type, url=current_url, screenshot_b64=current_screenshot
        ))
        history.append(format_history_entry(
            entry_type="comment", timestamp=get_current_timestamp(), content=comment
        ))
        if action != "DONE":
            history.append(format_history_entry(
                entry_type="action", timestamp=get_current_timestamp(),
                action={"type": action, "target": target}, reasoning=reasoning
            ))

        conversation_messages.append({"role": "assistant", "content": comment})

        await send("autonomous_step", {
            "screenshot": current_screenshot,
            "url": current_url,
            "page_type": current_page_type,
            "page_label": get_page_label(current_page_type),
            "comment": comment,
            "action": action,
            "target": target,
            "reasoning": reasoning,
            "persona_name": persona.name.split(" - ")[0],
            "step": nav_state.current_step,
            "max_steps": max_steps,
            "suggestions": get_suggestions(current_page_type),
            "history": history
        })

        # Pausa tra step
        await asyncio.sleep(3)

    await send("autonomous_done", {"reason": "max_steps", "history": history})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
