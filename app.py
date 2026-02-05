"""Hybrid UX Inspector - FastAPI Backend (fully async)."""

import io
import json
import base64
import asyncio
import logging
import traceback
from typing import Optional
from contextlib import asynccontextmanager

from PIL import Image
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from personas import (
    get_all_personas, get_persona, get_system_prompt,
    get_insights_prompt, customize_persona, OBJECTIVES
)
from suggestions import get_suggestions
from browser import BrowserManager, DESKTOP_VIEWPORT, MOBILE_VIEWPORT
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


def crop_highlight_area(screenshot_b64: str, x1: int, y1: int, x2: int, y2: int) -> str:
    """Ritaglia l'area evidenziata dallo screenshot originale."""
    img_bytes = base64.b64decode(screenshot_b64)
    img = Image.open(io.BytesIO(img_bytes))
    # Clamp coordinates to image bounds
    x1c = max(0, min(int(x1), img.width))
    y1c = max(0, min(int(y1), img.height))
    x2c = max(0, min(int(x2), img.width))
    y2c = max(0, min(int(y2), img.height))
    if x2c <= x1c or y2c <= y1c:
        # Fallback: return original if crop area is invalid
        return screenshot_b64
    cropped = img.crop((x1c, y1c, x2c, y2c))
    buffer = io.BytesIO()
    cropped.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


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


app = FastAPI(title="Hybrid UX Inspector", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/personas")
async def get_personas():
    personas = get_all_personas()
    return [
        {
            "id": p.id, "name": p.name, "description": p.short_description,
            "icon": p.icon, "color": p.color, "full_profile": p.full_profile
        }
        for p in personas
    ]


@app.get("/api/objectives")
async def get_objectives():
    return OBJECTIVES


@app.get("/api/suggestions/{page_type}")
async def get_page_suggestions(page_type: str):
    return get_suggestions(page_type)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
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
    custom_persona = None
    current_viewport = "desktop"

    async def send(event: str, data: dict):
        await websocket.send_json({"event": event, **data})

    def get_active_persona():
        if custom_persona:
            return custom_persona
        return get_persona(persona_id)

    try:
        claude = AIClient()

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            # === START ===
            if action == "start":
                persona_id = msg.get("persona_id", "marco")
                url = msg.get("url", "")
                mode = msg.get("mode", "hybrid")
                max_steps = msg.get("max_steps", 5)
                site_context = msg.get("site_context", "")
                current_viewport = msg.get("viewport", "desktop")

                custom_profile = msg.get("custom_profile", "")
                if custom_profile:
                    base_persona = get_persona(persona_id)
                    custom_persona = customize_persona(base_persona, custom_profile=custom_profile)

                if not url:
                    await send("error", {"message": "URL mancante"})
                    continue

                await send("status", {"message": "Avvio browser..."})
                logger.info("Starting browser for session %s (viewport: %s)", session_id, current_viewport)

                browser = BrowserManager()
                await browser.start(viewport=current_viewport)

                screenshot, final_url = await browser.navigate(url)
                page_type = await detect_page_type(screenshot, claude)

                current_url = final_url
                current_page_type = page_type
                current_screenshot = screenshot
                browser_sessions[session_id] = browser

                nav_state = NavigationState(max_steps=max_steps)
                nav_state.record_visit(final_url, page_type)

                history.append(format_history_entry(
                    entry_type="navigation", timestamp=get_current_timestamp(),
                    page_type=page_type, url=final_url, screenshot_b64=screenshot
                ))

                persona = get_active_persona()
                vp = browser.get_viewport_size()

                # No auto-comment in hybrid mode - user requests comments on demand
                await send("navigation", {
                    "screenshot": screenshot, "url": final_url,
                    "page_type": page_type, "page_label": get_page_label(page_type),
                    "comment": "", "persona_name": persona.name.split(" - ")[0],
                    "suggestions": get_suggestions(page_type),
                    "step": nav_state.current_step, "max_steps": nav_state.max_steps,
                    "history": history, "viewport": current_viewport,
                    "vp_width": vp["width"], "vp_height": vp["height"]
                })

                if mode == "autonomous":
                    objective_id = msg.get("objective", "first_impression")
                    await run_autonomous(
                        websocket, browser, claude, persona_id,
                        objective_id, nav_state, history,
                        conversation_messages, current_url,
                        current_page_type, current_screenshot,
                        max_steps, send, site_context, get_active_persona
                    )

            # === INPUT ===
            elif action == "input":
                user_input = msg.get("text", "").strip()
                if not user_input or not browser or not claude:
                    continue

                persona = get_active_persona()
                system_prompt = get_system_prompt(persona, site_context=site_context)
                await send("status", {"message": "Analizzo..."})

                input_type, content = await claude.classify_input(user_input)

                if input_type == "NAVIGATE":
                    await send("status", {"message": "Navigazione..."})

                    result = await execute_navigation_command(
                        browser=browser, command=content,
                        current_url=current_url, page_type=current_page_type,
                        claude_client=claude
                    )

                    current_url = result.get("url", current_url)
                    current_page_type = result.get("page_type", "other")
                    current_screenshot = result.get("screenshot", "")

                    history.append(format_history_entry(
                        entry_type="navigation", timestamp=get_current_timestamp(),
                        page_type=current_page_type, url=current_url,
                        screenshot_b64=current_screenshot
                    ))

                    # No auto-comment, just update browser
                    await send("navigation", {
                        "screenshot": current_screenshot, "url": current_url,
                        "page_type": current_page_type,
                        "page_label": get_page_label(current_page_type),
                        "comment": "", "persona_name": "",
                        "suggestions": get_suggestions(current_page_type),
                        "history": history
                    })

                else:
                    # Domanda - persona risponde (esplicito)
                    history.append(format_history_entry(
                        entry_type="question", timestamp=get_current_timestamp(),
                        content=user_input
                    ))
                    answer = await claude.chat(
                        system_prompt=system_prompt, user_message=user_input,
                        conversation_history=conversation_messages,
                        image_base64=current_screenshot
                    )
                    history.append(format_history_entry(
                        entry_type="answer", timestamp=get_current_timestamp(),
                        content=answer
                    ))
                    conversation_messages.append({"role": "user", "content": user_input})
                    conversation_messages.append({"role": "assistant", "content": answer})

                    await send("answer", {
                        "question": user_input, "answer": answer,
                        "persona_name": persona.name.split(" - ")[0],
                        "history": history
                    })

            # === CLICK: silent navigation, no comment, fast ===
            elif action == "click":
                if not browser:
                    continue

                x, y = msg.get("x", 0), msg.get("y", 0)
                screenshot, new_url = await browser.click_at(int(x), int(y))

                current_screenshot = screenshot
                # Detect page type only if URL actually changed
                if new_url != current_url:
                    current_url = new_url
                    # Fire-and-forget page type detection to avoid blocking
                    try:
                        current_page_type = await detect_page_type(screenshot, claude)
                    except Exception:
                        pass

                history.append(format_history_entry(
                    entry_type="navigation", timestamp=get_current_timestamp(),
                    page_type=current_page_type, url=current_url, screenshot_b64=screenshot
                ))

                await send("navigation", {
                    "screenshot": screenshot, "url": current_url,
                    "page_type": current_page_type,
                    "page_label": get_page_label(current_page_type),
                    "comment": "", "persona_name": "",
                    "suggestions": get_suggestions(current_page_type),
                    "history": history
                })

            # === SCROLL ===
            elif action == "scroll":
                if not browser:
                    continue
                delta = msg.get("delta", 300)
                screenshot, new_url = await browser.scroll_by(int(delta))
                current_url = new_url
                current_screenshot = screenshot
                await send("screenshot_update", {"screenshot": screenshot, "url": new_url})

            # === COMMENT: on-demand persona comment ===
            elif action == "comment":
                if not browser or not claude:
                    continue

                await send("status", {"message": "La persona sta commentando..."})

                persona = get_active_persona()
                system_prompt = get_system_prompt(persona, site_context=site_context)

                comment = await claude.chat(
                    system_prompt=system_prompt,
                    user_message=f"Guarda questo screenshot della pagina ({get_page_label(current_page_type)}). Cosa ne pensi? Reagisci in modo naturale. (2-3 frasi)",
                    conversation_history=conversation_messages,
                    image_base64=current_screenshot
                )

                history.append(format_history_entry(
                    entry_type="comment", timestamp=get_current_timestamp(),
                    content=comment
                ))
                conversation_messages.append({"role": "assistant", "content": comment})

                await send("persona_comment", {
                    "comment": comment,
                    "persona_name": persona.name.split(" - ")[0]
                })

            # === NAVIGATE_URL: navigate to a new URL in-session ===
            elif action == "navigate_url":
                if not browser:
                    continue
                url = msg.get("url", "").strip()
                if not url:
                    continue

                await send("status", {"message": "Navigazione..."})

                screenshot, final_url = await browser.navigate(url)
                page_type = await detect_page_type(screenshot, claude)

                current_url = final_url
                current_page_type = page_type
                current_screenshot = screenshot

                if nav_state:
                    nav_state.record_visit(final_url, page_type)

                history.append(format_history_entry(
                    entry_type="navigation", timestamp=get_current_timestamp(),
                    page_type=page_type, url=final_url, screenshot_b64=screenshot
                ))

                vp = browser.get_viewport_size()
                await send("navigation", {
                    "screenshot": screenshot, "url": final_url,
                    "page_type": page_type, "page_label": get_page_label(page_type),
                    "comment": "", "persona_name": "",
                    "suggestions": get_suggestions(page_type),
                    "history": history,
                    "vp_width": vp["width"], "vp_height": vp["height"]
                })

            # === HIGHLIGHT ===
            elif action == "highlight":
                if not browser or not claude:
                    continue

                x1, y1 = msg.get("x1", 0), msg.get("y1", 0)
                x2, y2 = msg.get("x2", 0), msg.get("y2", 0)
                question = msg.get("question", "")

                await send("status", {"message": "Analizzo area evidenziata..."})

                persona = get_active_persona()
                system_prompt = get_system_prompt(persona, site_context=site_context)

                cropped_screenshot = crop_highlight_area(
                    current_screenshot, int(x1), int(y1), int(x2), int(y2)
                )

                prompt = "Ecco un ritaglio di un'area specifica della pagina web che l'utente vuole farti analizzare. "
                prompt += question if question else "Cosa ne pensi di questa area? Reagisci come faresti tu."

                q_text = question or "Cosa ne pensi di quest'area?"
                history.append(format_history_entry(
                    entry_type="question", timestamp=get_current_timestamp(),
                    content=f"[Area evidenziata] {q_text}"
                ))

                answer = await claude.chat(
                    system_prompt=system_prompt, user_message=prompt,
                    conversation_history=conversation_messages,
                    image_base64=cropped_screenshot
                )

                history.append(format_history_entry(
                    entry_type="answer", timestamp=get_current_timestamp(),
                    content=answer
                ))
                conversation_messages.append({"role": "user", "content": f"[Highlight] {q_text}"})
                conversation_messages.append({"role": "assistant", "content": answer})

                await send("highlight_answer", {
                    "question": q_text,
                    "answer": answer,
                    "persona_name": persona.name.split(" - ")[0],
                    "history": history
                })

            # === SET_VIEWPORT: silent, no comment ===
            elif action == "set_viewport":
                if not browser:
                    continue

                new_viewport = msg.get("viewport", "desktop")
                if new_viewport == current_viewport:
                    continue

                await send("status", {"message": f"Cambio a vista {'mobile' if new_viewport == 'mobile' else 'desktop'}..."})

                screenshot, new_url = await browser.set_viewport(new_viewport)
                current_viewport = new_viewport
                current_url = new_url
                current_screenshot = screenshot

                new_page_type = await detect_page_type(screenshot, claude)
                current_page_type = new_page_type

                history.append(format_history_entry(
                    entry_type="navigation", timestamp=get_current_timestamp(),
                    page_type=new_page_type, url=new_url
                ))

                vp = browser.get_viewport_size()
                await send("navigation", {
                    "screenshot": screenshot, "url": new_url,
                    "page_type": new_page_type, "page_label": get_page_label(new_page_type),
                    "comment": "", "persona_name": "",
                    "suggestions": get_suggestions(new_page_type),
                    "history": history, "viewport": current_viewport,
                    "vp_width": vp["width"], "vp_height": vp["height"]
                })

            # === INSIGHTS ===
            elif action == "insights":
                if not claude or not conversation_messages:
                    await send("error", {"message": "Nessuna sessione attiva per generare insights"})
                    continue

                await send("status", {"message": "Genero insights..."})
                persona = get_active_persona()

                summary_parts = []
                for entry in history:
                    etype = entry.get("type", "")
                    if etype == "navigation":
                        summary_parts.append(f"[Navigazione] {entry.get('page_type', '')} - {entry.get('url', '')}")
                    elif etype == "comment":
                        summary_parts.append(f"[Commento persona] {entry.get('content', '')}")
                    elif etype == "question":
                        summary_parts.append(f"[Domanda] {entry.get('content', '')}")
                    elif etype == "answer":
                        summary_parts.append(f"[Risposta persona] {entry.get('content', '')}")
                    elif etype == "action":
                        act = entry.get("action", {})
                        summary_parts.append(f"[Azione] {act.get('type', '')} {act.get('target', '')} - {entry.get('reasoning', '')}")

                insights_prompt = get_insights_prompt(
                    persona=persona, site_context=site_context,
                    conversation_summary="\n".join(summary_parts)
                )
                insights = await claude.chat(
                    system_prompt="Sei un UX researcher esperto. Rispondi in italiano.",
                    user_message=insights_prompt
                )
                await send("insights", {"content": insights, "persona_name": persona.name})

            # === EXPORT ===
            elif action == "export":
                md = export_session(
                    url=current_url, persona_id=persona_id,
                    mode=msg.get("mode", "hybrid"),
                    objective=msg.get("objective", ""), history=history
                )
                await send("export", {"markdown": md})

            elif action == "stop_autonomous":
                pass

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
    max_steps, send, site_context="", get_persona_fn=None
):
    """Esegue la navigazione autonoma."""
    from personas import get_navigation_prompt, get_objective_prompt

    persona = get_persona_fn() if get_persona_fn else get_persona(persona_id)
    objective_prompt = get_objective_prompt(objective_id)

    for step in range(max_steps - 1):
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            msg = json.loads(raw)
            if msg.get("action") == "stop_autonomous":
                await send("autonomous_done", {"reason": "stopped", "history": history})
                return
            if msg.get("action") == "pause_autonomous":
                await send("status", {"message": "In pausa..."})
                while True:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    if msg.get("action") == "resume_autonomous":
                        break
                    if msg.get("action") == "stop_autonomous":
                        await send("autonomous_done", {"reason": "stopped", "history": history})
                        return
                    if msg.get("action") == "input":
                        user_input = msg.get("text", "").strip()
                        if user_input:
                            system_prompt = get_system_prompt(persona, site_context=site_context)
                            history.append(format_history_entry(entry_type="question", timestamp=get_current_timestamp(), content=user_input))
                            answer = await claude.chat(system_prompt=system_prompt, user_message=user_input, conversation_history=conversation_messages, image_base64=current_screenshot)
                            history.append(format_history_entry(entry_type="answer", timestamp=get_current_timestamp(), content=answer))
                            conversation_messages.append({"role": "user", "content": user_input})
                            conversation_messages.append({"role": "assistant", "content": answer})
                            await send("answer", {"question": user_input, "answer": answer, "persona_name": persona.name.split(" - ")[0], "history": history})
        except asyncio.TimeoutError:
            pass

        await send("status", {"message": f"Step {nav_state.current_step + 1}/{max_steps}..."})

        prompt = get_navigation_prompt(
            persona=persona, objective=objective_prompt,
            page_type=current_page_type, current_url=current_url,
            visited_pages=nav_state.visited_pages,
            current_step=nav_state.current_step,
            max_steps=nav_state.max_steps, site_context=site_context
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

        if action == "DONE":
            history.append(format_history_entry(entry_type="comment", timestamp=get_current_timestamp(), content=comment))
            await send("autonomous_step", {
                "screenshot": current_screenshot, "url": current_url,
                "page_type": current_page_type, "page_label": get_page_label(current_page_type),
                "comment": comment, "action": action, "target": target, "reasoning": reasoning,
                "persona_name": persona.name.split(" - ")[0],
                "step": nav_state.current_step, "max_steps": max_steps,
                "suggestions": get_suggestions(current_page_type), "history": history
            })
            await send("autonomous_done", {"reason": "done", "history": history})
            return

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

        history.append(format_history_entry(entry_type="navigation", timestamp=get_current_timestamp(), page_type=current_page_type, url=current_url, screenshot_b64=current_screenshot))
        history.append(format_history_entry(entry_type="comment", timestamp=get_current_timestamp(), content=comment))
        if action != "DONE":
            history.append(format_history_entry(entry_type="action", timestamp=get_current_timestamp(), action={"type": action, "target": target}, reasoning=reasoning))

        conversation_messages.append({"role": "assistant", "content": comment})

        await send("autonomous_step", {
            "screenshot": current_screenshot, "url": current_url,
            "page_type": current_page_type, "page_label": get_page_label(current_page_type),
            "comment": comment, "action": action, "target": target, "reasoning": reasoning,
            "persona_name": persona.name.split(" - ")[0],
            "step": nav_state.current_step, "max_steps": max_steps,
            "suggestions": get_suggestions(current_page_type), "history": history
        })

        await asyncio.sleep(3)

    await send("autonomous_done", {"reason": "max_steps", "history": history})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
