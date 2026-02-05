"""Google Gemini API wrapper per vision e chat (async)."""

import os
import json
import re
import base64
from typing import Optional, List, Dict, Any

from google import genai
from google.genai import types

# Modelli
TEXT_MODEL = "gemini-2.0-flash"
VISION_MODEL = "gemini-2.5-flash-image"


class AIClient:
    """Client async per interagire con Gemini API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY non configurata")

        self.client = genai.Client(api_key=self.api_key)

    async def analyze_image(
        self,
        image_base64: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Analizza un'immagine con Gemini Vision."""
        contents = self._build_history(conversation_history)

        image_bytes = base64.b64decode(image_base64)
        parts = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            types.Part.from_text(text=user_prompt)
        ]
        contents.append(types.Content(role="user", parts=parts))

        response = await self.client.aio.models.generate_content(
            model=VISION_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1024
            )
        )

        return response.text

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        image_base64: Optional[str] = None
    ) -> str:
        """Chat con Gemini (testo o multimodale)."""
        contents = self._build_history(conversation_history)

        parts = []
        if image_base64:
            image_bytes = base64.b64decode(image_base64)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
        parts.append(types.Part.from_text(text=user_message))

        contents.append(types.Content(role="user", parts=parts))

        model = VISION_MODEL if image_base64 else TEXT_MODEL

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1024
            )
        )

        return response.text

    async def classify_input(self, user_input: str) -> tuple:
        """Classifica l'input dell'utente come comando o domanda."""
        prompt = f"""L'utente ha scritto: "{user_input}"

Classifica:
- Se e' un comando di navigazione (vai, clicca, scroll, apri, cerca, torna, indietro), rispondi: NAVIGATE|descrizione
- Se e' una domanda o richiesta di opinione, rispondi: QUESTION|domanda

Rispondi SOLO nel formato indicato."""

        response = await self.client.aio.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=256)
        )

        result = response.text.strip()

        if "|" in result:
            parts = result.split("|", 1)
            return parts[0].strip().upper(), parts[1].strip()

        return "QUESTION", user_input

    async def translate_command_to_action(
        self,
        command: str,
        current_url: str,
        page_type: str
    ) -> Dict[str, Any]:
        """Traduce un comando di navigazione in azione Playwright."""
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

        response = await self.client.aio.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=256)
        )

        result = response.text.strip()

        try:
            json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {"action": "scroll_down"}

    def parse_navigation_response(self, response: str) -> Dict[str, Any]:
        """Parsa la risposta di navigazione autonoma."""
        try:
            json_match = re.search(r'\{[^}]*"comment"[^}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {
            "comment": response[:200] if len(response) > 200 else response,
            "action": "DONE",
            "target": "",
            "reasoning": "Risposta non parsabile"
        }

    def _build_history(
        self,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> list:
        """Converte la cronologia conversazione nel formato Gemini."""
        contents = []
        if not conversation_history:
            return contents

        for msg in conversation_history:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content)]
                    )
                )

        return contents
