import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest
from pydantic import BaseModel

from paper_diff import llm_client_with_cache


def test_second_call_with_same_input_hits_cache_no_network(tmp_path, monkeypatch):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this.")
    cache_dir = tmp_path / "cache"

    calls = []

    def fake_call_model(prompt_text: str, input_text: str, max_tokens: int, schema=None) -> str:
        calls.append((prompt_text, input_text))
        return "the model's answer"

    monkeypatch.setattr(llm_client_with_cache, "_call_model", fake_call_model)

    first = llm_client_with_cache.ask(prompt_file, "some input text", cache_dir=cache_dir)
    second = llm_client_with_cache.ask(prompt_file, "some input text", cache_dir=cache_dir)

    assert first == "the model's answer"
    assert second == "the model's answer"
    assert len(calls) == 1


def test_different_input_is_a_cache_miss(tmp_path, monkeypatch):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this.")
    cache_dir = tmp_path / "cache"

    calls = []
    monkeypatch.setattr(
        llm_client_with_cache,
        "_call_model",
        lambda p, t, m, s=None: calls.append(t) or f"answer for {t}",
    )

    llm_client_with_cache.ask(prompt_file, "input one", cache_dir=cache_dir)
    llm_client_with_cache.ask(prompt_file, "input two", cache_dir=cache_dir)

    assert len(calls) == 2


def test_cache_is_written_to_disk(tmp_path, monkeypatch):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this.")
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        llm_client_with_cache, "_call_model", lambda p, t, m, s=None: "cached response"
    )

    llm_client_with_cache.ask(prompt_file, "input", cache_dir=cache_dir)

    cached_files = list(Path(cache_dir).glob("*.txt"))
    assert len(cached_files) == 1
    assert cached_files[0].read_text() == "cached response"


class _Reply(BaseModel):
    quote: str


class _OtherReply(BaseModel):
    quote: str
    note: str


def test_schema_reply_is_validated_and_keeps_special_characters(tmp_path, monkeypatch):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Quote it.")
    quote = 'the model\'s "x" \\times y\n| a | b |'
    monkeypatch.setattr(
        llm_client_with_cache,
        "_call_model",
        lambda p, t, m, s=None: json.dumps({"quote": quote}),
    )

    reply = llm_client_with_cache.ask(prompt_file, "in", cache_dir=tmp_path / "c", schema=_Reply)

    assert reply == _Reply(quote=quote)


def test_cache_key_changes_when_only_the_schema_changes():
    base = llm_client_with_cache._cache_key("prompt", "input")
    with_schema = llm_client_with_cache._cache_key("prompt", "input", _Reply)
    other_schema = llm_client_with_cache._cache_key("prompt", "input", _OtherReply)

    assert len({base, with_schema, other_schema}) == 3


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


def _fake_client(stop_reason: str, requests: list):
    message = SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text="ok")]
    )

    class _Messages:
        def stream(self, **request):
            requests.append(request)
            return _FakeStream(message)

    return lambda api_key: SimpleNamespace(messages=_Messages())


def test_call_model_streams_and_passes_schema(monkeypatch):
    requests = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", _fake_client("end_turn", requests))

    text = llm_client_with_cache._call_model("prompt", "input", 64_000, _Reply)

    assert text == "ok"
    assert requests[0]["output_format"] is _Reply
    assert requests[0]["max_tokens"] == 64_000


def test_refusal_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", _fake_client("refusal", []))

    with pytest.raises(RuntimeError, match="refused"):
        llm_client_with_cache._call_model("prompt", "input", 1000, _Reply)


def test_truncation_retries_with_doubled_budget_up_to_ceiling(monkeypatch):
    budgets = []

    def truncating(p, t, m, s=None):
        budgets.append(m)
        raise llm_client_with_cache._TruncatedResponse

    monkeypatch.setattr(llm_client_with_cache, "_call_model", truncating)

    with pytest.raises(RuntimeError, match="truncated"):
        llm_client_with_cache._call_model_with_retry("p", "t", 32_000, None)

    assert budgets == [32_000, 64_000, 128_000]
