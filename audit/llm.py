"""A small OpenAI-compatible chat client with tool calls, for the LLM-driven audit tools.

Works with any /chat/completions endpoint (Groq, a local Ollama or vLLM server, ...). Retries
rate limits and server errors with the provider's suggested delay, like the judge does.
"""

from __future__ import annotations

import json
import os
import re
import time

import httpx


class Client:
    def __init__(self, model: str, base_url: str, api_key_var: str, max_attempts: int = 8, timeout: float = 180):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_var, "")
        self.max_attempts, self.timeout = max_attempts, timeout

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **options) -> dict:
        """Send one chat turn; return the assistant message (content and any tool_calls)."""
        body = {"model": self.model, "messages": messages, **options}
        if tools:
            body["tools"] = tools
        for attempt in range(self.max_attempts):
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.api_key}"})
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]
            if r.status_code == 429 or r.status_code >= 500:
                wait = re.search(r"try again in ([\d.]+)s", r.text)
                time.sleep(min(float(wait.group(1)) + 1, 60) if wait else min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"chat request failed: HTTP {r.status_code}: {r.text[:200]}")
        raise RuntimeError("chat request failed: rate-limited on every attempt")


def tool(name: str, description: str, **params: dict) -> dict:
    """A function-tool schema: tool("sql_query", "Run SQL", query={"type": "string"})."""
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": params, "required": list(params)},
    }}


def tool_calls(message: dict) -> list[tuple[str, str, dict]]:
    """(call id, tool name, parsed arguments) for each tool call in an assistant message."""
    calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        calls.append((call.get("id", ""), fn.get("name", ""), args if isinstance(args, dict) else {}))
    return calls


def json_object(text: str) -> dict | None:
    """The last top-level JSON object in a reply that may wrap it in prose or a code fence."""
    text, decoder, found, i = text or "", json.JSONDecoder(), None, 0
    while (i := text.find("{", i)) != -1:
        try:
            value, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict):
            found = value
        i = end
    return found
