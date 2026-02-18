"""Playwright wrapper per browser automation (async API)."""

import base64
from typing import Optional, Tuple, List
from urllib.parse import urlparse, urlunparse
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

# Viewport presets
DESKTOP_VIEWPORT = {'width': 1280, 'height': 800}
MOBILE_VIEWPORT = {'width': 390, 'height': 844}

DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

# Extra HTTP headers to reduce bot detection / 403 blocks
EXTRA_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# JS snippet to hide webdriver flag from navigator
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['it-IT', 'it', 'en-US', 'en'] });
window.chrome = { runtime: {} };
"""

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
            timezone_id='Europe/Rome',
            is_mobile=is_mobile,
            has_touch=is_mobile,
            extra_http_headers=EXTRA_HEADERS,
        )
        await self._context.add_init_script(STEALTH_INIT_SCRIPT)
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

        response = None
        try:
            response = await self._page.goto(url, wait_until='domcontentloaded', timeout=15000)
        except Exception:
            try:
                response = await self._page.goto(url, wait_until='commit', timeout=15000)
            except Exception:
                pass

        # Check for HTTP errors (403 Forbidden, etc.)
        if response and response.status in (403, 401):
            raise RuntimeError(
                f"Il sito ha bloccato l'accesso automatizzato (HTTP {response.status}). "
                "Prova con un altro URL o verifica che il sito sia accessibile pubblicamente."
            )

        await self._page.wait_for_timeout(500)
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
                    await self._page.wait_for_load_state('domcontentloaded', timeout=5000)
                except Exception:
                    pass
            else:
                return False, "", self._page.url

        except Exception:
            try:
                await self._page.wait_for_load_state('domcontentloaded', timeout=3000)
            except Exception:
                pass

        await self._page.wait_for_timeout(500)
        await self._try_dismiss_cookies()

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return True, screenshot_b64, self._page.url

    async def scroll_down(self) -> Tuple[str, str]:
        """Scrolla la pagina verso il basso."""
        if not self._page:
            return "", ""

        await self._page.evaluate('window.scrollBy(0, window.innerHeight * 0.8)')
        await self._page.wait_for_timeout(300)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def scroll_up(self) -> Tuple[str, str]:
        """Scrolla la pagina verso l'alto."""
        if not self._page:
            return "", ""

        await self._page.evaluate('window.scrollBy(0, -window.innerHeight * 0.8)')
        await self._page.wait_for_timeout(300)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def click_at(self, x: int, y: int) -> Tuple[str, str]:
        """Clicca alle coordinate (x, y) del viewport usando click JS nativo."""
        if not self._page:
            return "", ""

        # Listen for popup pages (target="_blank" links)
        new_page = None

        def on_page(page):
            nonlocal new_page
            new_page = page

        self._context.on("page", on_page)

        # Use JS to dispatch real pointer/mouse events on the exact DOM element
        # This is more reliable than Playwright's mouse.click for interactive
        # elements (popups, buttons, links with JS handlers, etc.)
        await self._page.evaluate('''(coords) => {
            const el = document.elementFromPoint(coords.x, coords.y);
            if (!el) return;

            const evtInit = {
                bubbles: true, cancelable: true, view: window,
                clientX: coords.x, clientY: coords.y
            };
            el.dispatchEvent(new PointerEvent('pointerdown', evtInit));
            el.dispatchEvent(new MouseEvent('mousedown', evtInit));
            el.dispatchEvent(new PointerEvent('pointerup', evtInit));
            el.dispatchEvent(new MouseEvent('mouseup', evtInit));
            el.dispatchEvent(new MouseEvent('click', evtInit));

            // Also trigger .click() on the nearest interactive ancestor
            const target = el.closest(
                'a[href], button, [onclick], [role="button"], ' +
                'input, select, summary, label, [tabindex]'
            );
            if (target && target !== el) target.click();
        }''', {'x': x, 'y': y})

        await self._page.wait_for_timeout(300)

        # Handle popup (target="_blank")
        if new_page:
            try:
                await new_page.wait_for_load_state(
                    'domcontentloaded', timeout=5000
                )
            except Exception:
                pass
            self._page = new_page
        else:
            # Wait briefly for any navigation triggered by the click
            try:
                await self._page.wait_for_load_state(
                    'domcontentloaded', timeout=2000
                )
            except Exception:
                pass

        self._context.remove_listener("page", on_page)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def scroll_by(self, delta_y: int) -> Tuple[str, str]:
        """Scrolla la pagina di delta_y pixel."""
        if not self._page:
            return "", ""

        # Use scrollTo with explicit position for better compatibility with
        # sites that override or intercept scrollBy (e.g. Unieuro).
        await self._page.evaluate('''(dy) => {
            const y = window.scrollY || window.pageYOffset || 0;
            window.scrollTo({ top: y + dy, behavior: 'instant' });
        }''', delta_y)
        await self._page.wait_for_timeout(300)

        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    async def capture_full_page(self) -> List[str]:
        """Scrolla tutta la pagina catturando uno screenshot per ogni viewport.

        Ritorna una lista di screenshot base64 (top→bottom).
        Alla fine torna alla posizione di scroll originale.
        """
        if not self._page:
            return []

        # Get page dimensions
        dims = await self._page.evaluate('''() => ({
            scrollY: window.scrollY,
            scrollHeight: document.documentElement.scrollHeight,
            viewportHeight: window.innerHeight
        })''')

        original_scroll = dims['scrollY']
        total_height = dims['scrollHeight']
        vp_height = dims['viewportHeight']

        screenshots = []

        # Scroll to top first
        await self._page.evaluate('window.scrollTo(0, 0)')
        await self._page.wait_for_timeout(200)

        scroll_pos = 0
        max_sections = 15  # safety cap

        while scroll_pos < total_height and len(screenshots) < max_sections:
            screenshot_bytes = await self._page.screenshot(full_page=False)
            screenshots.append(base64.b64encode(screenshot_bytes).decode('utf-8'))

            scroll_pos += int(vp_height * 0.85)  # small overlap between sections
            if scroll_pos >= total_height:
                break

            await self._page.evaluate(f'window.scrollTo(0, {scroll_pos})')
            await self._page.wait_for_timeout(250)

        # Restore original scroll position
        await self._page.evaluate(f'window.scrollTo(0, {original_scroll})')

        return screenshots

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
            timezone_id='Europe/Rome',
            is_mobile=is_mobile,
            has_touch=is_mobile,
            extra_http_headers=EXTRA_HEADERS,
        )
        await self._context.add_init_script(STEALTH_INIT_SCRIPT)
        self._page = await self._context.new_page()

        # Ri-naviga all'URL corrente
        if current_url and current_url != "about:blank":
            try:
                await self._page.goto(current_url, wait_until='domcontentloaded', timeout=15000)
            except Exception:
                try:
                    await self._page.goto(current_url, wait_until='commit', timeout=15000)
                except Exception:
                    pass
            await self._page.wait_for_timeout(500)
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
        await self._page.wait_for_timeout(500)

        for selector in COOKIE_SELECTORS:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.click()
                        await self._page.wait_for_timeout(300)
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
