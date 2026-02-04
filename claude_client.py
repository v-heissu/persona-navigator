"""Anthropic API wrapper per vision e chat."""

import os
import json
import re
from typing import Optional, List, Dict, Any
import anthropic


# Modello da utilizzare
MODEL = "claude-sonnet-4-20250514"


class ClaudeClient:
    """Client per interagire con l'API Anthropic."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Inizializza il client.

        Args:
            api_key: API key Anthropic (default: da env ANTHROPIC_API_KEY)
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY non configurata")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def analyze_image(
        self,
        image_base64: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Analizza un'immagine con Claude Vision.

        Args:
            image_base64: Immagine in base64
            system_prompt: Prompt di sistema
            user_prompt: Prompt utente
            conversation_history: Storico conversazione opzionale

        Returns:
            Risposta di Claude
        """
        messages = []

        # Aggiungi storico conversazione se presente
        if conversation_history:
            messages.extend(conversation_history)

        # Aggiungi messaggio corrente con immagine
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": user_prompt
                }
            ]
        })

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        return response.content[0].text

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        image_base64: Optional[str] = None
    ) -> str:
        """
        Chat con Claude.

        Args:
            system_prompt: Prompt di sistema
            user_message: Messaggio utente
            conversation_history: Storico conversazione opzionale
            image_base64: Immagine opzionale da includere

        Returns:
            Risposta di Claude
        """
        messages = []

        # Aggiungi storico conversazione se presente
        if conversation_history:
            messages.extend(conversation_history)

        # Costruisci contenuto messaggio
        if image_base64:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": user_message
                }
            ]
        else:
            content = user_message

        messages.append({
            "role": "user",
            "content": content
        })

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        return response.content[0].text

    def classify_input(self, user_input: str) -> tuple:
        """
        Classifica l'input dell'utente come comando o domanda.

        Args:
            user_input: Input dell'utente

        Returns:
            Tupla (tipo, contenuto) dove tipo e' "NAVIGATE" o "QUESTION"
        """
        prompt = f"""L'utente ha scritto: "{user_input}"

Classifica:
- Se e' un comando di navigazione (vai, clicca, scroll, apri, cerca, torna, indietro), rispondi: NAVIGATE|descrizione
- Se e' una domanda o richiesta di opinione, rispondi: QUESTION|domanda

Rispondi SOLO nel formato indicato."""

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )

        result = response.content[0].text.strip()

        if "|" in result:
            parts = result.split("|", 1)
            return parts[0].strip().upper(), parts[1].strip()

        # Default a domanda se non classificabile
        return "QUESTION", user_input

    def translate_command_to_action(
        self,
        command: str,
        current_url: str,
        page_type: str
    ) -> Dict[str, Any]:
        """
        Traduce un comando di navigazione in azione Playwright.

        Args:
            command: Comando dell'utente
            current_url: URL corrente
            page_type: Tipo di pagina corrente

        Returns:
            Dizionario con azione da eseguire
        """
        prompt = f"""Traduci questo comando di navigazione in azione Playwright.

Comando: "{command}"
URL corrente: "{current_url}"
Tipo pagina: "{page_type}"

Rispondi SOLO con JSON:
{{
  "action": "click|goto|scroll_down|scroll_up|back",
  "selector": "CSS selector se click",
  "url": "URL se goto"
}}

Selector comuni:
- menu -> nav a[href*="menu"], .menu-link, a:has-text("Menu")
- prenota/booking -> a[href*="book"], a[href*="prenota"], button:has-text("Prenota")
- contatti -> a[href*="contact"], a[href*="contatti"]
- chi siamo -> a[href*="about"], a[href*="chi-siamo"]"""

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )

        result = response.content[0].text.strip()

        # Estrai JSON dalla risposta
        try:
            # Cerca JSON nella risposta
            json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # Default: scroll down
        return {"action": "scroll_down"}

    def parse_navigation_response(self, response: str) -> Dict[str, Any]:
        """
        Parsa la risposta di navigazione autonoma.

        Args:
            response: Risposta di Claude

        Returns:
            Dizionario con comment, action, target, reasoning
        """
        try:
            # Cerca JSON nella risposta
            json_match = re.search(r'\{[^}]*"comment"[^}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # Fallback: estrai informazioni dal testo
        return {
            "comment": response[:200] if len(response) > 200 else response,
            "action": "DONE",
            "target": "",
            "reasoning": "Risposta non parsabile"
        }
