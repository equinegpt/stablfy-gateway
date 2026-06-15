"""Tests for the Gemini function-calling loop, with the HTTP layer mocked."""
import re

import httpx
import pytest
import respx

from nm_v1.clients.gemini import GeminiNotConfigured, chat_with_tools
from nm_v1.config import settings

_GEMINI_URL = re.compile(r"https://generativelanguage\.googleapis\.com/.*")


async def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    async def executor(name, args):
        return {}

    with pytest.raises(GeminiNotConfigured):
        await chat_with_tools(question="q", system_prompt="s", tools=[], executor=executor)


@respx.mock
async def test_runs_tool_then_returns_text(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    respx.post(_GEMINI_URL).mock(side_effect=[
        httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"functionCall": {"name": "get_today_mugs", "args": {}}}
        ]}}]}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "Three Full Mugs stand out today."}
        ]}}]}),
    ])

    called = []

    async def executor(name, args):
        called.append(name)
        return {"mugs": []}

    answer = await chat_with_tools(
        question="What are today's mugs?",
        system_prompt="sys",
        tools=[{"name": "get_today_mugs", "description": "x", "parameters": {"type": "object", "properties": {}}}],
        executor=executor,
    )
    assert answer == "Three Full Mugs stand out today."
    assert called == ["get_today_mugs"]


@respx.mock
async def test_direct_text_answer(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    respx.post(_GEMINI_URL).mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "G'day, ask me about today's racing."}]}}]
    }))

    async def executor(name, args):
        return {}

    answer = await chat_with_tools(question="hi", system_prompt="s", tools=[], executor=executor)
    assert "racing" in answer
