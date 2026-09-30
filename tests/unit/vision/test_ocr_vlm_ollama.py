"""Local Ollama VLM OCR fallback client (T116, SPEC F23, ADR-039/ADR-040).

DoD: the same typed (digit string, confidence)/"no answer" contract as T113's Anthropic client
(`ocr_vlm.py`), against a local Ollama server instead. Every test here is mocked end to end --
there is no real Ollama server call anywhere in this file (ADR-010's offline-test philosophy).
This file must collect and pass whether or not the optional `ocr_vlm_ollama` SDK extra is
installed, so it never imports `ollama` itself.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rogaine.vision import ocr_vlm_ollama
from rogaine.vision.ocr_vlm import Outcome
from rogaine.vision.ocr_vlm_ollama import DEFAULT_BASE_URL, DEFAULT_MODEL, read_control_number

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\nnot-a-real-png-just-stand-in-bytes"


def _chat_response(digit_string: str, confidence: float) -> SimpleNamespace:
    """A minimal stand-in for the Ollama chat response shape this module reads."""
    content = json.dumps({"digit_string": digit_string, "confidence": confidence})
    return SimpleNamespace(message=SimpleNamespace(content=content))


class _FakeClient:
    """Stand-in for `ollama.Client()` -- the injectable client this module accepts."""

    def __init__(
        self, result: SimpleNamespace | None = None, exc: BaseException | None = None
    ) -> None:
        self._result = result
        self._exc = exc
        self.calls: list[dict] = []

    def chat(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


class _ConnectionShapedError(Exception):
    """Stands in for a local-server connection failure without requiring the optional SDK."""


class TestWellFormedRead:
    """(a) a legible chat response with high confidence returns a populated result."""

    def test_legible_high_confidence_response_returns_populated_result(self) -> None:
        client = _FakeClient(result=_chat_response("31", 0.94))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.READ
        assert result.digit_string == "31"
        assert result.confidence == pytest.approx(0.94)
        assert len(client.calls) == 1

    def test_default_model_is_qwen_vl_and_is_passed_through(self) -> None:
        client = _FakeClient(result=_chat_response("7", 0.5))

        read_control_number(_IMAGE_BYTES, client=client)

        assert DEFAULT_MODEL == "qwen2.5vl:7b"
        assert client.calls[0]["model"] == DEFAULT_MODEL

    def test_model_parameter_overrides_the_default(self) -> None:
        client = _FakeClient(result=_chat_response("7", 0.5))

        read_control_number(_IMAGE_BYTES, model="llava:13b", client=client)

        assert client.calls[0]["model"] == "llava:13b"

    def test_structured_output_schema_matches_t113s_tool_input_shape(self) -> None:
        client = _FakeClient(result=_chat_response("7", 0.5))

        read_control_number(_IMAGE_BYTES, client=client)

        schema = client.calls[0]["format"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"digit_string", "confidence"}

    def test_default_base_url_is_the_local_ollama_port(self) -> None:
        assert DEFAULT_BASE_URL == "http://localhost:11434"


class TestCouldNotRead:
    """(b) a well-formed response signalling "could not read" is the typed no-answer outcome."""

    def test_empty_digit_string_returns_no_answer(self) -> None:
        client = _FakeClient(result=_chat_response("", 0.0))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    def test_no_answer_is_distinct_from_a_low_confidence_real_read(self) -> None:
        low_confidence_read = read_control_number(
            _IMAGE_BYTES, client=_FakeClient(result=_chat_response("9", 0.05))
        )
        could_not_read = read_control_number(
            _IMAGE_BYTES, client=_FakeClient(result=_chat_response("", 0.0))
        )

        assert low_confidence_read.outcome is Outcome.READ
        assert low_confidence_read.digit_string == "9"
        assert could_not_read.outcome is Outcome.NO_ANSWER
        assert could_not_read.digit_string is None

    @pytest.mark.parametrize("malformed", ["12a", " 7", "1234", "-5", "٣", "7 ", "1.5"])
    def test_malformed_digit_string_is_treated_as_unread(self, malformed: str) -> None:
        """T117/M-2: the model's digit string is validated client-side (`[0-9]{1,3}`); anything
        else is the same typed no-answer as any other malformed response, never a READ."""
        client = _FakeClient(result=_chat_response(malformed, 0.9))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    @pytest.mark.parametrize("ok", ["0", "7", "42", "201"])
    def test_one_to_three_ascii_digits_still_read(self, ok: str) -> None:
        client = _FakeClient(result=_chat_response(ok, 0.9))
        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.READ
        assert result.digit_string == ok


class TestMissingSdk:
    """(c) no `ollama` SDK installed -> no-answer, and no client is ever constructed or called."""

    def test_missing_sdk_returns_no_answer_without_constructing_a_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ocr_vlm_ollama, "ollama", None)

        result = read_control_number(_IMAGE_BYTES)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None


class TestClientFailuresDegradeGracefully:
    """(d) any client failure -> no-answer, never raises."""

    def test_connection_failure_returns_no_answer_never_raises(self) -> None:
        client = _FakeClient(exc=_ConnectionShapedError("connection refused"))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    def test_malformed_json_response_returns_no_answer_never_raises(self) -> None:
        malformed = SimpleNamespace(message=SimpleNamespace(content="not json"))
        client = _FakeClient(result=malformed)

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    def test_response_missing_expected_fields_returns_no_answer_never_raises(self) -> None:
        malformed = SimpleNamespace(
            message=SimpleNamespace(content=json.dumps({"unexpected": True}))
        )
        client = _FakeClient(result=malformed)

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None
