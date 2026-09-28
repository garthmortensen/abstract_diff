from pathlib import Path

from paper_diff import llm_client_with_cache


def test_second_call_with_same_input_hits_cache_no_network(tmp_path, monkeypatch):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this.")
    cache_dir = tmp_path / "cache"

    calls = []

    def fake_call_model(prompt_text: str, input_text: str, max_tokens: int) -> str:
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
        lambda p, t, m: calls.append(t) or f"answer for {t}",
    )

    llm_client_with_cache.ask(prompt_file, "input one", cache_dir=cache_dir)
    llm_client_with_cache.ask(prompt_file, "input two", cache_dir=cache_dir)

    assert len(calls) == 2


def test_cache_is_written_to_disk(tmp_path, monkeypatch):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Summarize this.")
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(llm_client_with_cache, "_call_model", lambda p, t, m: "cached response")

    llm_client_with_cache.ask(prompt_file, "input", cache_dir=cache_dir)

    cached_files = list(Path(cache_dir).glob("*.txt"))
    assert len(cached_files) == 1
    assert cached_files[0].read_text() == "cached response"
