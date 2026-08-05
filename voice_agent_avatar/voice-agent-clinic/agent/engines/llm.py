"""
LLM engines — free-tier providers for voice agent.
Supports Gemini, Groq, and Ollama with streaming and function calling.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# GEMINI 3.5 FLASH — free tier, 1500 req/day
# ─────────────────────────────────────────────────────────────────────────────

class GeminiEngine:
    """
    Gemini 3.5 Flash — Free tier, powerful LLM for voice agent.
    Streams responses for low latency.
    Free tier: 1500 requests/day, 15 req/min, 1M tokens/min
    """

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash"):
        import google.generativeai as genai
        from google.generativeai.types import HarmCategory, HarmBlockThreshold

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }

        self.generation_config = genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=256,
            top_p=0.95,
        )

        logger.info(f"Gemini engine initialized: {model}")

    async def chat(self, messages: List[Dict[str, str]], system_prompt: str) -> str:
        """Synchronous chat response."""
        import google.generativeai as genai

        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        last_message = messages[-1]["content"] if messages else ""
        chat = self.model.start_chat(history=history, system_instruction=system_prompt)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: chat.send_message(
                last_message,
                generation_config=self.generation_config,
                safety_settings=self.safety_settings,
            ),
        )
        return response.text

    async def chat_stream(
        self, messages: List[Dict[str, str]], system_prompt: str
    ) -> AsyncIterator[str]:
        """Streaming chat — yields text chunks."""
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        last_message = messages[-1]["content"] if messages else ""
        chat = self.model.start_chat(history=history, system_instruction=system_prompt)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: chat.send_message(
                last_message,
                generation_config=self.generation_config,
                safety_settings=self.safety_settings,
                stream=True,
            ),
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    async def function_call(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        functions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Function calling with Gemini. Returns text response or function call request."""
        tools = []
        for func in functions:
            tool = {
                "function_declarations": [
                    {
                        "name": func["name"],
                        "description": func["description"],
                        "parameters": func.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                ]
            }
            tools.append(tool)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.model.generate_content(
                contents=[{"role": "user", "parts": [messages[-1]["content"]]}],
                tools=tools,
                system_instruction=system_prompt,
                generation_config=self.generation_config,
                safety_settings=self.safety_settings,
            ),
        )

        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if part.function_call:
                return {
                    "type": "function_call",
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args),
                }
            else:
                return {"type": "text", "text": part.text}

        return {"type": "text", "text": response.text}


# ─────────────────────────────────────────────────────────────────────────────
# GROQ — fastest free tier (Llama 3.3 70B, 800 tok/s, 144k tok/day)
# ─────────────────────────────────────────────────────────────────────────────

class GroqEngine:
    """
    Groq API — Free tier with Llama 3.3 70B.
    800 tokens/sec, 144k tokens/day free.
    """

    def __init__(self, api_key: str = None, model: str = "llama-3.3-70b-versatile"):
        from groq import AsyncGroq

        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        logger.info(f"Groq engine initialized: {model}")

    async def chat(self, messages: list, system_prompt: str) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=0.3,
            max_tokens=256,
            top_p=0.95,
        )
        return response.choices[0].message.content

    async def chat_stream(self, messages: list, system_prompt: str):
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=0.3,
            max_tokens=256,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA — self-hosted, zero API cost
# ─────────────────────────────────────────────────────────────────────────────

class OllamaEngine:
    """
    Self-hosted Ollama — zero API cost, full control.
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.3:70b"):
        import httpx

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=60.0)
        logger.info(f"Ollama engine: {model} @ {base_url}")

    async def chat(self, messages: list, system_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 256,
            },
        }

        resp = await self.client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]

    async def chat_stream(self, messages: list, system_prompt: str):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": True,
            "options": {
                "temperature": 0.3,
                "num_predict": 256,
            },
        }

        async with self.client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                    except json.JSONDecodeError:
                        continue
