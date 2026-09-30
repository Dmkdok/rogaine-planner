"""VLM OCR fallback client for control numbers (T113, SPEC F23, ADR-039).

ADR-009 picked Tesseract over a VLM for the *default* control-number read, explicitly because OCR
quality must never gate a route: Tesseract is allowed to be weak, and an unreadable number simply
comes back `number=None` plus a flag (see `rogaine.vision.ocr`'s own docstring). ADR-039 is a
narrow reversal of that decision, not a replacement of it: circle/position detection stays 100%
classical CV, untouched by this module, and Tesseract stays the default reader. This module only
adds an *opt-in* fallback for the cases Tesseract already flags as unreadable -- a second attempt
at the same crop via the Anthropic API, wired in by T114 behind `[ocr_fallback].enabled` (shipped
`false`).

Everything in this module is designed to stay inert unless explicitly configured on:

- The API key is read directly from `ANTHROPIC_API_KEY` (never from `config/default.toml` or any
  committed file). No key means `read_control_number` returns `VlmOcrResult.no_answer()` *before*
  ever constructing a real `anthropic.Anthropic()` client or attempting any network call.
- `anthropic` is an optional dependency (the `ocr_vlm` extra in `pyproject.toml`), not a base one --
  a base install / the default test run never pulls in a network-capable SDK. If the package is not
  installed, the module still imports cleanly and behaves exactly like the no-key case.
- This function never raises. Every failure mode -- no key, the SDK missing, a network error, a
  rate limit, a malformed tool response, anything -- degrades to the same typed "no answer" outcome,
  matching F8/F23's "never a crash, never blocking a route" requirement (ADR-010's offline-test
  philosophy for the suite; ADR-039 for this feature specifically).

A fallback-resolved control must be marked distinctly from a Tesseract-sourced read (SPEC F23) --
that marking, and the trigger condition itself, is T114's job. This module only builds the
standalone client.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised only without the optional `ocr_vlm` extra
    anthropic = None  # type: ignore[assignment]

#: Cost/latency matches this model's documented niche far better than a larger one: reading 1-3
#: printed digits from a small cropped circle is a narrow, high-volume, low-complexity
#: classification call, not a task that benefits from extra capability. Configurable per-call
#: (T114 wires a `model` field into `[ocr_fallback]`) -- this constant is only the default.
DEFAULT_MODEL = "claude-haiku-4-5"

_TOOL_NAME = "read_control_number"
_MAX_TOKENS = 256

# Most-specific-first exception chain (anthropic SDK docs' own recommended shape). Each tuple is
# empty when `anthropic` is not installed, so the `except <tuple>:` clauses below simply never
# match and every failure falls through to the final broad catch -- same outcome either way.
_RATE_LIMIT_ERRORS: tuple[type[BaseException], ...]
_API_STATUS_ERRORS: tuple[type[BaseException], ...]
_API_CONNECTION_ERRORS: tuple[type[BaseException], ...]
if anthropic is not None:
    _RATE_LIMIT_ERRORS = (anthropic.RateLimitError,)
    _API_STATUS_ERRORS = (anthropic.APIStatusError,)
    _API_CONNECTION_ERRORS = (anthropic.APIConnectionError,)
else:  # pragma: no cover - exercised only without the optional `ocr_vlm` extra
    _RATE_LIMIT_ERRORS = ()
    _API_STATUS_ERRORS = ()
    _API_CONNECTION_ERRORS = ()

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": (
        "Report the printed control number read from the cropped orienteering map circle, or an "
        "empty digit_string when it cannot be read."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "digit_string": {
                "type": "string",
                "description": (
                    "1 to 3 ASCII digits (e.g. '31', '104'), or an empty string when the control "
                    "number cannot be read."
                ),
                "pattern": "^[0-9]{1,3}$|^$",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in the reading, from 0.0 (no idea) to 1.0 (certain).",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["digit_string", "confidence"],
        "additionalProperties": False,
    },
}

_INSTRUCTION_TEXT = (
    "This image is a cropped region of an orienteering map around one control circle. Read the "
    "printed control number (1 to 3 digits) shown inside or beside the circle. Respond only by "
    "calling the read_control_number tool."
)


class Outcome(StrEnum):
    """What a VLM OCR attempt produced."""

    #: The model returned a non-empty digit string -- a real read, at whatever confidence.
    READ = "read"
    #: No usable answer: missing/unconfigured key, SDK missing, network/API failure, or the model
    #: itself reported it could not read the number. Distinct from a low-confidence real read.
    NO_ANSWER = "no_answer"


@dataclass(frozen=True)
class VlmOcrResult:
    """The outcome of one `read_control_number` call.

    `digit_string` is `None` exactly when `outcome is Outcome.NO_ANSWER` -- callers should branch
    on `outcome`, not on truthiness of `digit_string` alone, so a legitimate (if unlikely) reading
    of "0" is never mistaken for "no answer".
    """

    outcome: Outcome
    digit_string: str | None
    confidence: float

    @classmethod
    def no_answer(cls) -> VlmOcrResult:
        return cls(outcome=Outcome.NO_ANSWER, digit_string=None, confidence=0.0)


def _build_request_kwargs(image_bytes: bytes, model: str) -> dict[str, Any]:
    encoded = base64.standard_b64encode(image_bytes).decode("ascii")
    return {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "tools": [_TOOL_SCHEMA],
        "tool_choice": {"type": "tool", "name": _TOOL_NAME},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": _INSTRUCTION_TEXT},
                ],
            }
        ],
    }


def _parse_tool_response(response: Any) -> VlmOcrResult:
    """Pull the forced tool call's structured input out of a Messages API response.

    Raises on anything unexpected (no matching `tool_use` block, missing/malformed fields) --
    `read_control_number`'s broad `except Exception` folds that into the same "no answer" outcome
    as a network failure, never propagating a parse error to the caller.
    """
    for block in response.content:
        is_target_tool_use = (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _TOOL_NAME
        )
        if is_target_tool_use:
            tool_input = dict(block.input)
            digit_string = str(tool_input["digit_string"])
            confidence = float(tool_input["confidence"])
            if not digit_string.strip():
                return VlmOcrResult.no_answer()
            if not re.fullmatch(r"[0-9]{1,3}", digit_string):
                raise ValueError(f"malformed digit_string: {digit_string!r}")
            return VlmOcrResult(
                outcome=Outcome.READ,
                digit_string=digit_string,
                confidence=max(0.0, min(1.0, confidence)),
            )
    raise ValueError("no read_control_number tool_use block in the response")


def read_control_number(
    image_bytes: bytes,
    *,
    model: str = DEFAULT_MODEL,
    client: anthropic.Anthropic | None = None,
) -> VlmOcrResult:
    """Read a control's printed number from its cropped ink region via the Anthropic API.

    `image_bytes` is the crop's PNG-encoded bytes (T114 produces the crop; this module only
    reads it). `client` is injectable so callers -- and tests -- can supply a fake/mock without
    monkeypatching the SDK globally; when omitted, a real `anthropic.Anthropic()` is constructed
    from `ANTHROPIC_API_KEY`, but only if that variable is set and the optional `ocr_vlm` SDK
    dependency is installed.

    Never raises. Every failure -- no key, the SDK not installed, a rate limit, a connection
    error, any other API error, or a malformed tool response -- returns
    `VlmOcrResult.no_answer()` instead (SPEC F8/F23: OCR failure degrades the run, never aborts
    it; ADR-039 keeps this fully offline/deterministic whenever unconfigured).
    """
    active_client = client
    if active_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key or anthropic is None:
            return VlmOcrResult.no_answer()
        active_client = anthropic.Anthropic(api_key=api_key)

    try:
        response = active_client.messages.create(**_build_request_kwargs(image_bytes, model))
        return _parse_tool_response(response)
    except _RATE_LIMIT_ERRORS:
        return VlmOcrResult.no_answer()
    except _API_STATUS_ERRORS:
        return VlmOcrResult.no_answer()
    except _API_CONNECTION_ERRORS:
        return VlmOcrResult.no_answer()
    except Exception:
        return VlmOcrResult.no_answer()
