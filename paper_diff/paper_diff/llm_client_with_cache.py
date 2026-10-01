"""The only module that imports an LLM SDK.

Every stage module that needs a model result calls `ask()` here instead of
talking to a provider directly. Swapping providers, or stubbing calls out for
tests, touches this one file.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TypeVar, overload

from pydantic import BaseModel

# Every stage uses the one model picked here. Set USER_CHOICE to the number of
# the model you want, then run the pipeline as usual. Each entry is
# (label, API model id, maximum output tokens the model can write in one reply).
MODELS = [
    ("Sonnet 5.5", "claude-sonnet-5-5", 128_000),  # 1
    ("Haiku 4.5", "claude-haiku-4-5-20251001", 64_000),  # 2
    ("Fable 5.1", "claude-fable-5-1", 128_000),  # 3
    ("Opus 5.5", "claude-opus-5-5", 128_000),  # 4
]
USER_CHOICE = 1
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".llm_cache"
_API_KEY_VAR = "ANTHROPIC_API_KEY"

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def selected_model() -> tuple[str, str, int]:
    """The `(label, model id, max output tokens)` entry `USER_CHOICE` points at."""
    if not 1 <= USER_CHOICE <= len(MODELS):
        listing = ", ".join(f"{i}={label}" for i, (label, _, _) in enumerate(MODELS, start=1))
        raise ValueError(f"USER_CHOICE={USER_CHOICE} is not a valid choice. Use one of: {listing}")
    return MODELS[USER_CHOICE - 1]


@overload
def ask(
    prompt_file: Path,
    input_text: str,
    cache_dir: Path = ...,
    max_tokens: int = ...,
    schema: None = ...,
) -> str: ...


@overload
def ask(
    prompt_file: Path,
    input_text: str,
    cache_dir: Path = ...,
    max_tokens: int = ...,
    *,
    schema: type[SchemaT],
) -> SchemaT: ...


def ask(
    prompt_file: Path,
    input_text: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    max_tokens: int = 4096,
    schema: type[BaseModel] | None = None,
):
    """Send `input_text` through the prompt in `prompt_file`, cached by content hash.

    In: a prompt file (plain markdown instructions), the text to run it on,
    a token budget for the response, and optionally a Pydantic `schema`.
    With a schema, the API's structured outputs constrain the reply to JSON
    matching it, so quotes, backslashes, and LaTeX in the text can never
    break parsing.
    Out: the model's raw text, or, with a schema, a validated instance of
    it. Identical across repeated calls with the same prompt, input, and
    schema because the second call is served from disk.
    Belongs to: the LLM boundary used by every `*_llm.py` stage module.
    """
    prompt_text = prompt_file.read_text()
    cache_key = _cache_key(prompt_text, input_text, schema, selected_model()[1])
    cache_path = cache_dir / f"{cache_key}.txt"
    if cache_path.exists():
        response = cache_path.read_text()
    else:
        response = _call_model_with_retry(prompt_text, input_text, max_tokens, schema)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(response)
    if schema is None:
        return response
    return schema.model_validate_json(response)


def _cache_key(
    prompt_text: str,
    input_text: str,
    schema: type[BaseModel] | None = None,
    model_id: str = "",
) -> str:
    """Hash of everything that shapes the reply.

    The model id is included so a reply cached from one model is never served
    for another. The schema is included only when given.
    """
    digest = hashlib.sha256()
    digest.update(model_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(prompt_text.encode("utf-8"))
    digest.update(b"\0")
    digest.update(input_text.encode("utf-8"))
    if schema is not None:
        digest.update(b"\0")
        digest.update(json.dumps(schema.model_json_schema(), sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


class _TruncatedResponse(Exception):
    pass


# The largest output any listed model can write. Streaming (see `_call_model`) is what makes a
# ceiling this high usable; a blocking request is refused past ~20K tokens.
_RETRY_CEILING = 128_000


def _call_model_with_retry(
    prompt_text: str, input_text: str, max_tokens: int, schema: type[BaseModel] | None
) -> str:
    """Double the token budget and retry when the model's response was truncated.

    A caller's length-based estimate can undershoot when an input yields more
    output than its size predicts (e.g. a section with many assertions
    compared against a small counterpart); this recovers from that without
    every caller needing an ever-larger fixed floor.
    """
    ceiling = min(_RETRY_CEILING, selected_model()[2])
    budget = min(max_tokens, ceiling)
    while True:
        try:
            return _call_model(prompt_text, input_text, budget, schema)
        except _TruncatedResponse:
            if budget >= ceiling:
                raise RuntimeError(
                    f"Response still truncated at max_tokens={budget} after retrying "
                    "with a doubled budget; split this input."
                ) from None
            budget = min(budget * 2, ceiling)


def _call_model(
    prompt_text: str, input_text: str, max_tokens: int, schema: type[BaseModel] | None = None
) -> str:
    """One streamed request, returned as the complete reply text.

    Streaming keeps the connection active while the model writes, so long
    replies don't hit the SDK's ~10-minute limit on blocking requests.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=_api_key_from_environment())
    request = {
        "model": selected_model()[1],
        "max_tokens": max_tokens,
        "system": prompt_text,
        "messages": [{"role": "user", "content": input_text}],
    }
    if schema is not None:
        request["output_config"] = {"format": _json_schema_format(schema)}
    with client.messages.stream(**request) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "max_tokens":
        raise _TruncatedResponse
    if message.stop_reason == "refusal":
        raise RuntimeError(
            f"The model refused this request (prompt starts {prompt_text[:60]!r}); "
            "its reply is not usable."
        )
    return "".join(block.text for block in message.content if block.type == "text")


def _json_schema_format(schema: type[BaseModel]) -> dict:
    """The request's output format for `schema`, built the way the SDK would.

    Passed as plain `output_config` rather than the SDK's `output_format=`
    because the SDK then parses each text block as it closes, which is before
    the stop reason arrives. A reply cut off at `max_tokens` would raise a
    JSON parse error instead of reaching the truncation retry. `ask()`
    validates the finished text against the schema itself.
    """
    from anthropic.lib._parse._transform import transform_schema

    return {"type": "json_schema", "schema": transform_schema(schema.model_json_schema())}


def _api_key_from_environment() -> str:
    """Read the API key from the shell environment (e.g. exported in ~/.bashrc)."""
    api_key = os.environ.get(_API_KEY_VAR)
    if not api_key:
        raise RuntimeError(
            f"{_API_KEY_VAR} is not set. Export it in your shell rc file, e.g. "
            f"`export {_API_KEY_VAR}='sk-ant-...'` in ~/.bashrc, then open a new shell."
        )
    return api_key
