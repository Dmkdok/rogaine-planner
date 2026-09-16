"""Local Ollama VLM OCR fallback client for control numbers (T116, SPEC F23, ADR-039/ADR-040).

ADR-040 adds this module as a sibling to `ocr_vlm.py` (T113, unmodified): a second, free/local
backend for the same opt-in OCR-number fallback, selected via `[ocr_fallback].provider = "ollama"`
(`vision/ocr.py::_try_vlm_fallback` does the dispatch). This module owes its entire typed contract
to T113 -- `VlmOcrResult`/`Outcome` are imported from `ocr_vlm`, not redefined, and the JSON schema
sent as Ollama's structured-output `format` is the same `input_schema` T113 built for Anthropic's
forced tool call, so both backends read a control's digits into exactly the same shape.

Everything in this module stays inert unless explicitly configured on, mirroring T113's own
guarantee:

- `ollama` is an optional dependency (the `ocr_vlm_ollama` extra in `pyproject.toml`), not a base
  one -- a base install / the default test run never pulls in a network-capable client. If the
  package is not installed, the module still imports cleanly and behaves exactly like an
  unreachable server.
- This function never raises. A missing SDK, an unreachable/erroring local server, or a malformed
  response all degrade to the same typed "no answer" outcome as T113 (F8/F23's "never a crash,
  never blocking a route"). Unlike T113's Anthropic path, there is no distinct rate-limit/status/
  connection exception chain to preserve here -- every failure mode gets identical treatment (no
  retry, no differentiated logging), so one broad catch is the whole story, not a simplification
  of a richer one.
"""

from __future__ import annotations

import json
from typing import Any

try:
    import ollama
except ImportError:  # pragma: no cover - exercised only without the optional `ocr_vlm_ollama` extra
    ollama = None  # type: ignore[assignment]

from rogaine.vision.ocr_vlm import _TOOL_SCHEMA, Outcome, VlmOcrResult

#: `qwen2.5vl` is a small local vision model well-suited to reading 1-3 printed digits from a
#: small cropped circle -- the same cost/capability match `ocr_vlm.py`'s own `DEFAULT_MODEL`
#: comment makes for Haiku, just at $0 instead of a per-call price. Configurable per-call
#: (`[ocr_fallback].model`) -- this constant is only the default.
DEFAULT_MODEL = "qwen2.5vl:7b"

#: Ollama's own default local port. Configurable via `[ocr_fallback].base_url`.
DEFAULT_BASE_URL = "http://localhost:11434"

_INSTRUCTION_TEXT = (
    "This image is a cropped region of an orienteering map around one control circle. Read the "
    "printed control number (1 to 3 digits) shown inside or beside the circle. Respond with the "
    "digit_string and your confidence."
)

#: Reuses T113's own tool input schema verbatim -- both backends read a control's digits into the
#: exact same `{digit_string, confidence}` shape, one schema, not two hand-kept copies.
_RESPONSE_SCHEMA: dict[str, Any] = _TOOL_SCHEMA["input_schema"]


def _parse_chat_response(response: Any) -> VlmOcrResult:
    """Pull the structured JSON payload out of an Ollama chat response.

    Raises on anything unexpected (missing content, invalid JSON, missing fields) --
    `read_control_number`'s broad `except Exception` folds that into the same "no answer" outcome
    as a connection failure, never propagating a parse error to the caller.
    """
    payload = json.loads(response.message.content)
    digit_string = str(payload["digit_string"]).strip()
    confidence = float(payload["confidence"])
    if not digit_string:
        return VlmOcrResult.no_answer()
    return VlmOcrResult(
        outcome=Outcome.READ,
        digit_string=digit_string,
        confidence=max(0.0, min(1.0, confidence)),
    )


def read_control_number(
    image_bytes: bytes,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    client: ollama.Client | None = None,
) -> VlmOcrResult:
    """Read a control's printed number from its cropped ink region via a local Ollama server.

    Same contract as `ocr_vlm.read_control_number` (T113): `image_bytes` is the crop's PNG-encoded
    bytes (T114 produces the crop; this module only reads it), `client` is injectable so callers
    -- and tests -- can supply a fake/mock without monkeypatching the SDK globally, and this
    function never raises. `client` omitted constructs a real `ollama.Client(host=base_url)`, but
    only if the optional `ocr_vlm_ollama` SDK dependency is installed; there is no API key to
    check, since a local server has none.
    """
    active_client = client
    if active_client is None:
        if ollama is None:
            return VlmOcrResult.no_answer()
        active_client = ollama.Client(host=base_url)

    try:
        response = active_client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": _INSTRUCTION_TEXT,
                    "images": [image_bytes],
                }
            ],
            format=_RESPONSE_SCHEMA,
        )
        return _parse_chat_response(response)
    except Exception:
        return VlmOcrResult.no_answer()
