"""Logica per la navigazione autonoma (async)."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urlunparse

from personas import Persona, get_navigation_prompt, get_objective_prompt
from ai_client import AIClient
from browser import BrowserManager
from page_detector import detect_page_type


@dataclass
class NavigationState:
    """Stato della navigazione autonoma."""

    max_steps: int = 5
    current_step: int = 0
    visited_urls: set = field(default_factory=set)
    visited_pages: List[Dict[str, str]] = field(default_factory=list)
    scroll_count_current_page: int = 0
    max_scrolls_per_page: int = 3

    def can_continue(self) -> bool:
        return self.current_step < self.max_steps

    def should_visit(self, url: str) -> bool:
        normalized = self._normalize_url(url)
        return normalized not in self.visited_urls

    def can_scroll(self) -> bool:
        return self.scroll_count_current_page < self.max_scrolls_per_page

    def record_visit(self, url: str, page_type: str) -> None:
        normalized = self._normalize_url(url)
        self.visited_urls.add(normalized)
        self.visited_pages.append({"url": url, "type": page_type})
        self.current_step += 1
        self.scroll_count_current_page = 0

    def record_scroll(self) -> None:
        self.scroll_count_current_page += 1

    def reset(self) -> None:
        self.current_step = 0
        self.visited_urls = set()
        self.visited_pages = []
        self.scroll_count_current_page = 0

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/'),
            '', '', ''
        ))


class AutonomousNavigator:
    """Gestisce la navigazione autonoma della persona (async)."""

    def __init__(
        self,
        persona: Persona,
        objective_id: str,
        max_steps: int = 5,
        claude_client: Optional[AIClient] = None,
        browser: Optional[BrowserManager] = None
    ):
        self.persona = persona
        self.objective_prompt = get_objective_prompt(objective_id)
        self.state = NavigationState(max_steps=max_steps)
        self.claude_client = claude_client or AIClient()
        self.browser = browser or BrowserManager()
        self.is_paused = False
        self.is_stopped = False

    async def start(self, url: str) -> Dict[str, Any]:
        """Avvia la navigazione."""
        await self.browser.start()
        screenshot, final_url = await self.browser.navigate(url)
        page_type = await detect_page_type(screenshot, self.claude_client)
        self.state.record_visit(final_url, page_type)
        result = await self._get_persona_action(screenshot, page_type, final_url)

        return {
            "screenshot": screenshot,
            "url": final_url,
            "page_type": page_type,
            "comment": result.get("comment", ""),
            "action": result.get("action", "DONE"),
            "target": result.get("target", ""),
            "reasoning": result.get("reasoning", ""),
            "step": self.state.current_step,
            "max_steps": self.state.max_steps,
            "is_done": result.get("action") == "DONE" or not self.state.can_continue()
        }

    async def next_step(self) -> Dict[str, Any]:
        """Esegue il prossimo passo di navigazione."""
        if self.is_stopped or not self.state.can_continue():
            return {"is_done": True}

        screenshot = await self.browser.get_screenshot()
        current_url = self.browser.get_current_url()
        page_type = await detect_page_type(screenshot, self.claude_client)
        result = await self._get_persona_action(screenshot, page_type, current_url)
        action = result.get("action", "DONE")
        target = result.get("target", "")

        if action == "CLICK" and target:
            success, new_screenshot, new_url = await self.browser.click_element(target)
            if success and self.state.should_visit(new_url):
                new_page_type = await detect_page_type(new_screenshot, self.claude_client)
                self.state.record_visit(new_url, new_page_type)
                screenshot = new_screenshot
                current_url = new_url
                page_type = new_page_type
            elif not success:
                screenshot, current_url = await self.browser.scroll_down()
                self.state.record_scroll()

        elif action == "SCROLL_DOWN":
            if self.state.can_scroll():
                screenshot, current_url = await self.browser.scroll_down()
                self.state.record_scroll()
            else:
                action = "DONE"

        elif action == "BACK":
            screenshot, current_url = await self.browser.go_back()
            page_type = await detect_page_type(screenshot, self.claude_client)

        elif action == "DONE":
            pass

        is_done = action == "DONE" or not self.state.can_continue()

        return {
            "screenshot": screenshot,
            "url": current_url,
            "page_type": page_type,
            "comment": result.get("comment", ""),
            "action": action,
            "target": target,
            "reasoning": result.get("reasoning", ""),
            "step": self.state.current_step,
            "max_steps": self.state.max_steps,
            "is_done": is_done
        }

    def pause(self) -> None:
        self.is_paused = True

    def resume(self) -> None:
        self.is_paused = False

    def stop(self) -> None:
        self.is_stopped = True

    async def cleanup(self) -> None:
        await self.browser.stop()

    async def _get_persona_action(
        self,
        screenshot: str,
        page_type: str,
        current_url: str
    ) -> Dict[str, Any]:
        prompt = get_navigation_prompt(
            persona=self.persona,
            objective=self.objective_prompt,
            page_type=page_type,
            current_url=current_url,
            visited_pages=self.state.visited_pages,
            current_step=self.state.current_step,
            max_steps=self.state.max_steps
        )

        response = await self.claude_client.analyze_image(
            image_base64=screenshot,
            system_prompt=f"Sei {self.persona.name.split(' - ')[0]}. Rispondi solo in JSON.",
            user_prompt=prompt
        )

        return self.claude_client.parse_navigation_response(response)


async def execute_navigation_command(
    browser: BrowserManager,
    command: str,
    current_url: str,
    page_type: str,
    claude_client: AIClient
) -> Dict[str, Any]:
    """Esegue un comando di navigazione in modalita' guidata (async)."""
    action_info = await claude_client.translate_command_to_action(
        command=command,
        current_url=current_url,
        page_type=page_type
    )

    action = action_info.get("action", "scroll_down")
    screenshot = ""
    new_url = current_url
    success = True

    if action == "click":
        selector = action_info.get("selector", "")
        if selector:
            success, screenshot, new_url = await browser.click_element(selector)
            if not success:
                success, screenshot, new_url = await browser.click_element(command)

    elif action == "goto":
        url = action_info.get("url", "")
        if url:
            screenshot, new_url = await browser.navigate(url)

    elif action == "scroll_down":
        screenshot, new_url = await browser.scroll_down()

    elif action == "scroll_up":
        screenshot, new_url = await browser.scroll_up()

    elif action == "back":
        screenshot, new_url = await browser.go_back()

    else:
        screenshot, new_url = await browser.scroll_down()

    if not screenshot:
        screenshot = await browser.get_screenshot()

    new_page_type = await detect_page_type(screenshot, claude_client)

    return {
        "screenshot": screenshot,
        "url": new_url,
        "page_type": new_page_type,
        "success": success
    }
