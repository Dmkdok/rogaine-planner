"""VLM OCR fallback client (T113, SPEC F23, ADR-039).

DoD: a client wrapper that takes a control's cropped ink region and returns a structured
(digit string, confidence) result or a typed "no answer" outcome; reads its API key from
`ANTHROPIC_API_KEY` only; never raises. Every test here is mocked end to end -- there is no real
network call anywhere in this file (ADR-010's offline-test philosophy). The fake/stand-in
exception classes below stand in for `anthropic.RateLimitError` / `APIConnectionError` on purpose:
this file must collect and pass whether or not the optional `ocr_vlm` SDK extra is installed, so
it never imports `anthropic` itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rogaine.vision import ocr_vlm
from rogaine.vision.ocr_vlm import DEFAULT_MODEL, Outcome, read_control_number

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\nnot-a-real-png-just-stand-in-bytes"


def _tool_response(digit_string: str, confidence: float) -> SimpleNamespace:
    """A minimal stand-in for the Messages API response shape this module reads."""
    block = SimpleNamespace(
        type="tool_use",
        name="read_control_number",
        input={"digit_string": digit_string, "confidence": confidence},
    )
    return SimpleNamespace(content=[block])


class _FakeMessages:
    """Stand-in for `anthropic.Anthropic().messages` -- returns or raises on demand."""

    def __init__(
        self, result: SimpleNamespace | None = None, exc: BaseException | None = None
    ) -> None:
        self._result = result
        self._exc = exc
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


class _FakeClient:
    """Stand-in for `anthropic.Anthropic()` -- the injectable client this module accepts."""

    def __init__(
        self, result: SimpleNamespace | None = None, exc: BaseException | None = None
    ) -> None:
        self.messages = _FakeMessages(result=result, exc=exc)


class _RateLimitShapedError(Exception):
    """Stands in for `anthropic.RateLimitError` without requiring the optional SDK."""


class _ConnectionShapedError(Exception):
    """Stands in for `anthropic.APIConnectionError` without requiring the optional SDK."""


class TestWellFormedRead:
    """(a) a legible tool response with high confidence returns a populated result."""

    def test_legible_high_confidence_response_returns_populated_result(self) -> None:
        client = _FakeClient(result=_tool_response("31", 0.94))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.READ
        assert result.digit_string == "31"
        assert result.confidence == pytest.approx(0.94)
        assert len(client.messages.calls) == 1

    def test_default_model_is_haiku_and_is_passed_through(self) -> None:
        client = _FakeClient(result=_tool_response("7", 0.5))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.READ
        assert DEFAULT_MODEL == "claude-haiku-4-5"
        assert client.messages.calls[0]["model"] == DEFAULT_MODEL

    def test_model_parameter_overrides_the_default(self) -> None:
        client = _FakeClient(result=_tool_response("7", 0.5))

        read_control_number(_IMAGE_BYTES, model="claude-opus-5", client=client)

        assert client.messages.calls[0]["model"] == "claude-opus-5"

    def test_tool_use_is_forced_with_a_strict_schema(self) -> None:
        client = _FakeClient(result=_tool_response("7", 0.5))

        read_control_number(_IMAGE_BYTES, client=client)

        sent = client.messages.calls[0]
        assert sent["tool_choice"] == {"type": "tool", "name": "read_control_number"}
        assert sent["tools"][0]["strict"] is True
        assert sent["tools"][0]["input_schema"]["additionalProperties"] is False


class TestCouldNotRead:
    """(b) a well-formed response signalling "could not read" is the typed no-answer outcome."""

    def test_empty_digit_string_returns_no_answer(self) -> None:
        client = _FakeClient(result=_tool_response("", 0.0))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    def test_no_answer_is_distinct_from_a_low_confidence_real_read(self) -> None:
        low_confidence_read = read_control_number(
            _IMAGE_BYTES, client=_FakeClient(result=_tool_response("9", 0.05))
        )
        could_not_read = read_control_number(
            _IMAGE_BYTES, client=_FakeClient(result=_tool_response("", 0.0))
        )

        assert low_confidence_read.outcome is Outcome.READ
        assert low_confidence_read.digit_string == "9"
        assert could_not_read.outcome is Outcome.NO_ANSWER
        assert could_not_read.digit_string is None

    @pytest.mark.parametrize("malformed", ["12a", " 7", "1234", "-5", "٣", "7 ", "1.5"])
    def test_malformed_digit_string_is_treated_as_unread(self, malformed: str) -> None:
        """T117/M-2: the model's digit string is validated client-side (`[0-9]{1,3}`); anything
        else is the same typed no-answer as any other malformed response, never a READ."""
        client = _FakeClient(result=_tool_response(malformed, 0.9))

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    @pytest.mark.parametrize("ok", ["0", "7", "42", "201"])
    def test_one_to_three_ascii_digits_still_read(self, ok: str) -> None:
        client = _FakeClient(result=_tool_response(ok, 0.9))
        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.READ
        assert result.digit_string == ok


class TestMissingApiKey:
    """(c) no `ANTHROPIC_API_KEY` -> no-answer, and no client is ever constructed or called."""

    def test_no_key_returns_no_answer_without_constructing_a_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        fake_sdk = MagicMock()
        monkeypatch.setattr(ocr_vlm, "anthropic", fake_sdk)

        result = read_control_number(_IMAGE_BYTES)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None
        fake_sdk.Anthropic.assert_not_called()
        fake_sdk.Anthropic.return_value.messages.create.assert_not_called()

    def test_empty_string_key_is_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        fake_sdk = MagicMock()
        monkeypatch.setattr(ocr_vlm, "anthropic", fake_sdk)

        result = read_control_number(_IMAGE_BYTES)

        assert result.outcome is Outcome.NO_ANSWER
        fake_sdk.Anthropic.assert_not_called()


class TestClientFailuresDegradeGracefully:
    """(d) any client failure -> no-answer, never raises."""

    @pytest.mark.parametrize(
        "exc",
        [_RateLimitShapedError("rate limited"), _ConnectionShapedError("connection reset")],
    )
    def test_client_exception_returns_no_answer_never_raises(self, exc: Exception) -> None:
        client = _FakeClient(exc=exc)

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None

    def test_malformed_tool_response_returns_no_answer_never_raises(self) -> None:
        malformed = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
        client = _FakeClient(result=malformed)

        result = read_control_number(_IMAGE_BYTES, client=client)

        assert result.outcome is Outcome.NO_ANSWER
        assert result.digit_string is None
