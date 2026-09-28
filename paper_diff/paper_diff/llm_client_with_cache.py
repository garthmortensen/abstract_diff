"""The only module that imports an LLM SDK.

Every stage module that needs a model result calls `ask()` here instead of
talking to a provider directly. Swapping providers, or stubbing calls out for
tests, touches this one file.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

_MODEL = "claude-sonnet-5"
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".llm_cache"
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=_ENV_FILE)


def ask(
    prompt_file: Path,
    input_text: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    max_tokens: int = 4096,
) -> str:
    """Send `input_text` through the prompt in `prompt_file`, cached by content hash.

    In: a prompt file (plain markdown instructions), the text to run it on,
    and a token budget for the response (raise this for prompts, such as
    Stage 0's, that must echo back something as long as the input).
    Out: the model's raw text response, identical across repeated calls with
    the same prompt and input because the second call is served from disk.
    Belongs to: the LLM boundary used by every `*_llm.py` stage module.
    """
    prompt_text = prompt_file.read_text()
    cache_key = _cache_key(prompt_text, input_text)
    cache_path = cache_dir / f"{cache_key}.txt"
    if cache_path.exists():
        return cache_path.read_text()

    response = _call_model_with_retry(prompt_text, input_text, max_tokens)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(response)
    return response


def _cache_key(prompt_text: str, input_text: str) -> str:
    digest = hashlib.sha256()
    digest.update(prompt_text.encode("utf-8"))
    digest.update(b"\0")
    digest.update(input_text.encode("utf-8"))
    return digest.hexdigest()


class _TruncatedResponse(Exception):
    pass


_RETRY_CEILING = 20_000


def _call_model_with_retry(prompt_text: str, input_text: str, max_tokens: int) -> str:
    """Double the token budget and retry when the model's response was truncated.

    A caller's length-based estimate can undershoot when an input yields more
    output than its size predicts (e.g. a section with many assertions
    compared against a small counterpart); this recovers from that without
    every caller needing an ever-larger fixed floor.
    """
    budget = max_tokens
    while True:
        try:
            return _call_model(prompt_text, input_text, budget)
        except _TruncatedResponse:
            if budget >= _RETRY_CEILING:
                raise RuntimeError(
                    f"Response still truncated at max_tokens={budget} after retrying "
                    "with a doubled budget; raise the ceiling or split this input."
                ) from None
            budget = min(budget * 2, _RETRY_CEILING)


def _call_model(prompt_text: str, input_text: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=prompt_text,
        messages=[{"role": "user", "content": input_text}],
    )
    if message.stop_reason == "max_tokens":
        raise _TruncatedResponse
    return "".join(block.text for block in message.content if block.type == "text")
