"""Local OpenAI-compatible proxy for free-tier model APIs.

- Retries 429 / 5xx responses with the provider's suggested delay instead of failing the episode.
- Strips assistant-message fields some providers reject when a harness echoes them back
  (Groq rejects gpt-oss's `channel`).
- Injects the upstream API key, so the key never has to be passed on a command line.

    UPSTREAM_BASE_URL=https://api.groq.com/openai/v1 UPSTREAM_API_KEY_VAR=GROQ_API_KEY \
        python scripts/llm_proxy.py            # listens on 127.0.0.1:8099
    vf-eval ... --client.base-url http://127.0.0.1:8099/v1 --client.api-key-var GROQ_API_KEY
"""

import asyncio
import json
import os
import re

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

UPSTREAM = os.environ.get("UPSTREAM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
API_KEY = os.environ[os.environ.get("UPSTREAM_API_KEY_VAR", "GROQ_API_KEY")]
STRIP_FIELDS = {f for f in os.environ.get("STRIP_ASSISTANT_FIELDS", "channel").split(",") if f}
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "12"))
PORT = int(os.environ.get("PROXY_PORT", "8099"))

client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20))


def clean(body: dict) -> dict:
    for message in body.get("messages", []):
        if message.get("role") == "assistant":
            for field in STRIP_FIELDS:
                message.pop(field, None)
    return body


def retry_delay(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header) + 0.5, 60)
        except ValueError:
            pass
    match = re.search(r"try again in ([\d.]+)(ms|s)", response.text)
    if match:
        value = float(match.group(1)) / (1000 if match.group(2) == "ms" else 1)
        return min(value + 0.5, 60)
    return min(2 ** attempt, 30)


async def proxy(request: Request) -> Response:
    path = request.url.path.removeprefix("/v1")
    raw = await request.body()
    try:
        payload = json.dumps(clean(json.loads(raw))).encode() if raw else raw
    except ValueError:
        payload = raw
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(MAX_ATTEMPTS):
        upstream = client.build_request(request.method, UPSTREAM + path, content=payload, headers=headers)
        response = await client.send(upstream, stream=True)
        if response.status_code == 429 or response.status_code >= 500:
            await response.aread()
            if attempt + 1 < MAX_ATTEMPTS:
                delay = retry_delay(response, attempt)
                print(f"[proxy] {response.status_code} on {path}, retrying in {delay:.1f}s", flush=True)
                await response.aclose()
                await asyncio.sleep(delay)
                continue
            return Response(response.content, response.status_code, media_type="application/json")
        media = response.headers.get("content-type", "application/json")
        if "text/event-stream" in media:
            async def body():
                async for chunk in response.aiter_raw():
                    yield chunk
                await response.aclose()
            return StreamingResponse(body(), response.status_code, media_type=media)
        content = await response.aread()
        await response.aclose()
        return Response(content, response.status_code, media_type=media)


app = Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
