"""Playwright wrapper per browser automation (async API)."""

import base64
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

# Viewport presets
DESKTOP_VIEWPORT = {'width': 1280, 'height': 800}
MOBILE_VIEWPORT = {'width': 390, 'height': 844}

DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

# Selettori comuni per cookie banner
COOKIE_SELECTORS = [
    # Comuni italiani
    "[id*='cookie'] button[id*='accept']",
    "[id*='cookie'] button[id*='accetta']",
    "[class*='cookie'] button[class*='accept']",
    "[class*='cookie'] button[class*='accetta']",
    "button:has-text('Accetta')",
    "button:has-text('Accetta tutti')",
    "button:has-text('Accept')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Accetto')",
    "button:has-text('OK')",
    "button:has-text('Agree')",
    # Provider comuni
    "#onetrust-accept-btn-handler",
    ".cc-accept",
    ".cc-btn.cc-allow",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "[data-cookiefirst-action='accept']",
    "#didomi-notice-agree-button",
    ".iubenda-cs-accept-btn",
    "#accept-cookie",
    ".accept-cookies",
    "[data-action='accept']",
    ".cookie-accept",
    "#cookie-accept",
    ".gdpr-accept",
    "#gdpr-accept",
]


class BrowserManager:
    """Gestisce il browser Playwright per la navigazione (async)."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self, viewport: str = "desktop") -> None:
        """Avvia il browser con viewport desktop o mobile."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )

        is_mobile = viewport == "mobile"
        vp = MOBILE_VIEWPORT if is_mobile else DESKTOP_VIEWPORT
        ua = MOBILE_UA if is_mobile else DESKTOP_UA
        self._current_viewport = viewport

        self._context = await self._browser.new_context(
            viewport=vp,
            user_agent=ua,
            locale='it-IT',
            is_mobile=is_mobile,
            has_touch=is_mobile
        )
        self._page = await self._context.new_page()

    async def stop(self) -> None:
        """Chiude il browser."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def navigate(self, url: str) -> Tuple[str, str]:
        """Naviga a un URL e restituisce screenshot e URL finale."""
        if not self._page:
            await self.start()

        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url

        try:
            await self._page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception:
            try:
                await self._page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception:
                pass

        await self._page.wait_for_timeout(1000)
        await self._try_dismiss_cookies()

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def click_element(self, selector_or_text: str) -> Tuple[bool, str, str]:
        """Clicca su un elemento."""
        if not self._page:
            return False, "", ""

        try:
            element = await self._page.query_selector(selector_or_text)

            if not element:
                element = await self._page.query_selector(f'text="{selector_or_text}"')

            if not element:
                element = await self._find_element_by_text(selector_or_text)

            if element:
                await element.click()
                try:
                    await self._page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
            else:
                return False, "", self._page.url

        except Exception:
            try:
                await self._page.wait_for_load_state('domcontentloaded', timeout=5000)
            except Exception:
                pass

        await self._page.wait_for_timeout(1000)
        await self._try_dismiss_cookies()

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return True, screenshot_b64, self._page.url

    async def scroll_down(self) -> Tuple[str, str]:
        """Scrolla la pagina verso il basso."""
        if not self._page:
            return "", ""

        await self._page.evaluate('window.scrollBy(0, window.innerHeight * 0.8)')
        await self._page.wait_for_timeout(500)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def scroll_up(self) -> Tuple[str, str]:
        """Scrolla la pagina verso l'alto."""
        if not self._page:
            return "", ""

        await self._page.evaluate('window.scrollBy(0, -window.innerHeight * 0.8)')
        await self._page.wait_for_timeout(500)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def click_at(self, x: int, y: int) -> Tuple[str, str]:
        """Clicca alle coordinate (x, y) del viewport."""
        if not self._page:
            return "", ""

        await self._page.mouse.click(x, y)
        try:
            await self._page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            pass

        await self._page.wait_for_timeout(1000)
        await self._try_dismiss_cookies()

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def scroll_by(self, delta_y: int) -> Tuple[str, str]:
        """Scrolla la pagina di delta_y pixel."""
        if not self._page:
            return "", ""

        await self._page.evaluate(f'window.scrollBy(0, {delta_y})')
        await self._page.wait_for_timeout(500)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def go_back(self) -> Tuple[str, str]:
        """Torna alla pagina precedente."""
        if not self._page:
            return "", ""

        await self._page.go_back()
        await self._page.wait_for_timeout(1000)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def set_viewport(self, viewport: str) -> Tuple[str, str]:
        """Cambia viewport (desktop/mobile) ricreando il contesto browser."""
        if not self._browser:
            return "", ""

        current_url = self._page.url if self._page else ""
        self._current_viewport = viewport

        # Chiudi contesto corrente
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()

        # Ricrea contesto con nuovo viewport
        is_mobile = viewport == "mobile"
        vp = MOBILE_VIEWPORT if is_mobile else DESKTOP_VIEWPORT
        ua = MOBILE_UA if is_mobile else DESKTOP_UA

        self._context = await self._browser.new_context(
            viewport=vp,
            user_agent=ua,
            locale='it-IT',
            is_mobile=is_mobile,
            has_touch=is_mobile
        )
        self._page = await self._context.new_page()

        # Ri-naviga all'URL corrente
        if current_url and current_url != "about:blank":
            try:
                await self._page.goto(current_url, wait_until='networkidle', timeout=30000)
            except Exception:
                try:
                    await self._page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
                except Exception:
                    pass
            await self._page.wait_for_timeout(1000)
            await self._try_dismiss_cookies()

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        return screenshot_b64, self._page.url

    def get_viewport_size(self) -> dict:
        """Restituisce le dimensioni del viewport corrente."""
        if hasattr(self, '_current_viewport') and self._current_viewport == "mobile":
            return MOBILE_VIEWPORT
        return DESKTOP_VIEWPORT

    async def get_screenshot(self) -> str:
        """Cattura uno screenshot della pagina corrente."""
        if not self._page:
            return ""

        screenshot_bytes = await self._page.screenshot(full_page=False)
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def get_current_url(self) -> str:
        """Restituisce l'URL corrente."""
        if not self._page:
            return ""
        return self._page.url

    async def _try_dismiss_cookies(self) -> bool:
        """Tenta di chiudere cookie banner. Best effort."""
        await self._page.wait_for_timeout(1000)

        for selector in COOKIE_SELECTORS:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.click()
                        await self._page.wait_for_timeout(500)
                        return True
            except Exception:
                continue

        return False

    async def _find_element_by_text(self, text: str):
        """Trova un elemento tramite testo contenuto."""
        text_lower = text.lower()

        links = await self._page.query_selector_all('a')
        for link in links:
            try:
                link_text = await link.inner_text()
                if text_lower in link_text.lower():
                    return link
            except Exception:
                continue

        buttons = await self._page.query_selector_all('button')
        for button in buttons:
            try:
                button_text = await button.inner_text()
                if text_lower in button_text.lower():
                    return button
            except Exception:
                continue

        clickables = await self._page.query_selector_all('[role="button"], [role="link"]')
        for elem in clickables:
            try:
                elem_text = await elem.inner_text()
                if text_lower in elem_text.lower():
                    return elem
            except Exception:
                continue

        return None


def normalize_url(url: str) -> str:
    """Normalizza un URL rimuovendo query params e trailing slash."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', '', ''))
