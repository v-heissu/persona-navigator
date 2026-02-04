"""Playwright wrapper per browser automation (sync API)."""

import base64
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext


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
    """Gestisce il browser Playwright per la navigazione."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def start(self) -> None:
        """Avvia il browser."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        self._context = self._browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='it-IT'
        )
        self._page = self._context.new_page()

    def stop(self) -> None:
        """Chiude il browser."""
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def navigate(self, url: str) -> Tuple[str, str]:
        """
        Naviga a un URL e restituisce screenshot e URL finale.

        Args:
            url: URL da visitare

        Returns:
            Tupla (screenshot_base64, final_url)
        """
        if not self._page:
            self.start()

        # Assicura che l'URL abbia il protocollo
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url

        try:
            self._page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception:
            # Fallback se networkidle timeout
            self._page.goto(url, wait_until='domcontentloaded', timeout=30000)

        # Attendi un po' per il rendering
        self._page.wait_for_timeout(1000)

        # Tenta di chiudere cookie banner
        self._try_dismiss_cookies()

        # Cattura screenshot
        screenshot_bytes = self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    def click_element(self, selector_or_text: str) -> Tuple[bool, str, str]:
        """
        Clicca su un elemento.

        Args:
            selector_or_text: Selettore CSS o testo dell'elemento

        Returns:
            Tupla (success, screenshot_base64, final_url)
        """
        if not self._page:
            return False, "", ""

        try:
            # Prova prima come selettore CSS
            element = self._page.query_selector(selector_or_text)

            if not element:
                # Prova con il testo
                element = self._page.query_selector(f'text="{selector_or_text}"')

            if not element:
                # Prova con ricerca piu' flessibile
                element = self._find_element_by_text(selector_or_text)

            if element:
                element.click()
                try:
                    self._page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
            else:
                return False, "", self._page.url

        except Exception:
            try:
                self._page.wait_for_load_state('domcontentloaded', timeout=5000)
            except Exception:
                pass

        self._page.wait_for_timeout(1000)
        self._try_dismiss_cookies()

        screenshot_bytes = self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return True, screenshot_b64, self._page.url

    def scroll_down(self) -> Tuple[str, str]:
        """
        Scrolla la pagina verso il basso.

        Returns:
            Tupla (screenshot_base64, current_url)
        """
        if not self._page:
            return "", ""

        self._page.evaluate('window.scrollBy(0, window.innerHeight * 0.8)')
        self._page.wait_for_timeout(500)

        screenshot_bytes = self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    def scroll_up(self) -> Tuple[str, str]:
        """
        Scrolla la pagina verso l'alto.

        Returns:
            Tupla (screenshot_base64, current_url)
        """
        if not self._page:
            return "", ""

        self._page.evaluate('window.scrollBy(0, -window.innerHeight * 0.8)')
        self._page.wait_for_timeout(500)

        screenshot_bytes = self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    def go_back(self) -> Tuple[str, str]:
        """
        Torna alla pagina precedente.

        Returns:
            Tupla (screenshot_base64, current_url)
        """
        if not self._page:
            return "", ""

        self._page.go_back()
        self._page.wait_for_timeout(1000)

        screenshot_bytes = self._page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return screenshot_b64, self._page.url

    def get_screenshot(self) -> str:
        """
        Cattura uno screenshot della pagina corrente.

        Returns:
            Screenshot in base64
        """
        if not self._page:
            return ""

        screenshot_bytes = self._page.screenshot(full_page=False)
        return base64.b64encode(screenshot_bytes).decode('utf-8')

    def get_current_url(self) -> str:
        """Restituisce l'URL corrente."""
        if not self._page:
            return ""
        return self._page.url

    def _try_dismiss_cookies(self) -> bool:
        """
        Tenta di chiudere cookie banner. Best effort.

        Returns:
            True se un banner e' stato chiuso
        """
        self._page.wait_for_timeout(1000)

        for selector in COOKIE_SELECTORS:
            try:
                element = self._page.query_selector(selector)
                if element:
                    is_visible = element.is_visible()
                    if is_visible:
                        element.click()
                        self._page.wait_for_timeout(500)
                        return True
            except Exception:
                continue

        return False

    def _find_element_by_text(self, text: str):
        """
        Trova un elemento tramite testo contenuto.

        Args:
            text: Testo da cercare

        Returns:
            Elemento trovato o None
        """
        text_lower = text.lower()

        # Cerca in link
        links = self._page.query_selector_all('a')
        for link in links:
            try:
                link_text = link.inner_text()
                if text_lower in link_text.lower():
                    return link
            except Exception:
                continue

        # Cerca in bottoni
        buttons = self._page.query_selector_all('button')
        for button in buttons:
            try:
                button_text = button.inner_text()
                if text_lower in button_text.lower():
                    return button
            except Exception:
                continue

        # Cerca in elementi con role
        clickables = self._page.query_selector_all('[role="button"], [role="link"]')
        for elem in clickables:
            try:
                elem_text = elem.inner_text()
                if text_lower in elem_text.lower():
                    return elem
            except Exception:
                continue

        return None


def normalize_url(url: str) -> str:
    """
    Normalizza un URL rimuovendo query params e trailing slash.

    Args:
        url: URL da normalizzare

    Returns:
        URL normalizzato
    """
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', '', ''))
