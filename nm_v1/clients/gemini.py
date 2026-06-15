"""Gemini client with a function-calling loop.

Drives a multi-round conversation: send the user's question plus tool
declarations, and whenever Gemini asks to call a tool, run it and feed the
result back, until Gemini returns a text answer (or we hit the round cap).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from nm_v1.config import settings

ToolExecutor = Callable[[str, dict], Awaitable[dict]]


class GeminiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GeminiNotConfigured(GeminiError):
    pass


def _history_to_contents(history: list[dict] | None) -> list[dict]:
    contents: list[dict] = []
    for turn in history or []:
        role = "user" if turn.get("role") == "user" else "model"
        text = turn.get("text") or ""
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    return contents


async def chat_with_tools(
    *,
    question: str,
    system_prompt: str,
    tools: list[dict],
    executor: ToolExecutor,
    history: list[dict] | None = None,
) -> str:
    if not settings.GEMINI_API_KEY:
        raise GeminiNotConfigured("GEMINI_API_KEY not configured", status_code=503)

    url = (
        f"{settings.GEMINI_BASE_URL.rstrip('/')}"
        f"/models/{settings.GEMINI_MODEL}:generateContent"
        f"?key={settings.GEMINI_API_KEY}"
    )

    contents = _history_to_contents(history)
    contents.append({"role": "user", "parts": [{"text": question}]})

    base = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"functionDeclarations": tools}],
    }

    async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS) as client:
        for _ in range(settings.ASK_MAX_TOOL_ROUNDS):
            try:
                resp = await client.post(url, json={**base, "contents": contents})
            except httpx.HTTPError as exc:
                raise GeminiError(f"Gemini request failed: {exc}") from exc
            if resp.status_code >= 400:
                raise GeminiError(
                    f"Gemini returned {resp.status_code}: {resp.text[:200]}",
                    status_code=resp.status_code,
                )

            candidates = resp.json().get("candidates") or []
            if not candidates:
                raise GeminiError("Gemini returned no candidates")
            parts = (candidates[0].get("content") or {}).get("parts") or []

            calls = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
            if calls:
                contents.append({"role": "model", "parts": [{"functionCall": c} for c in calls]})
                responses = []
                for call in calls:
                    name = call.get("name", "")
                    args = call.get("args") or {}
                    try:
                        result = await executor(name, args)
                    except Exception as exc:  # surface tool failure to the model
                        result = {"error": str(exc)}
                    responses.append({
                        "functionResponse": {"name": name, "response": {"result": result}}
                    })
                contents.append({"role": "user", "parts": responses})
                continue

            text = "".join(
                p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p
            ).strip()
            if text:
                return text
            raise GeminiError("Gemini returned neither text nor a tool call")

    raise GeminiError("Gemini exceeded the tool-call round limit")
