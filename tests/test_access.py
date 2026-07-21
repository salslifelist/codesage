"""Tests for the minimal per-session judging access gate."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

import app
import codesage.config as config_module
from codesage.config import read_ai_access_configuration, verify_judge_access_code
from codesage.source import normalise_pasted_source
from codesage.ui import ANALYSIS_KEY, handle_actions


CONFIGURED_ENVIRONMENT = {
    "AI_ENABLED": "true",
    "JUDGE_ACCESS_CODE": "shared-judge-code",
    "OPENAI_API_KEY": "sk-test",
    "OPENAI_MODEL": "gpt-5.6-sol",
}


@pytest.mark.parametrize("enabled", ["1", "true", "TRUE", "yes", "on", " On "])
def test_enabled_values_make_complete_configuration_available(enabled):
    environment = {**CONFIGURED_ENVIRONMENT, "AI_ENABLED": enabled}

    configuration = read_ai_access_configuration(environment)

    assert configuration.available is True
    assert configuration.model == "gpt-5.6-sol"


@pytest.mark.parametrize("enabled", ["", "0", "false", "no", "off", "unexpected"])
def test_missing_or_disabled_configuration_is_unavailable(enabled):
    environment = {**CONFIGURED_ENVIRONMENT, "AI_ENABLED": enabled}
    assert read_ai_access_configuration(environment).available is False

    missing_code = {**CONFIGURED_ENVIRONMENT, "JUDGE_ACCESS_CODE": ""}
    missing_key = {**CONFIGURED_ENVIRONMENT, "OPENAI_API_KEY": ""}
    assert read_ai_access_configuration(missing_code).available is False
    assert read_ai_access_configuration(missing_key).available is False


def test_access_code_verification_uses_complete_configuration():
    assert verify_judge_access_code("shared-judge-code", CONFIGURED_ENVIRONMENT) is True
    assert verify_judge_access_code("wrong", CONFIGURED_ENVIRONMENT) is False
    assert (
        verify_judge_access_code(
            "shared-judge-code", {**CONFIGURED_ENVIRONMENT, "AI_ENABLED": "false"}
        )
        is False
    )


def test_access_code_verification_uses_constant_time_comparison(monkeypatch):
    comparisons = []

    def compare_digest(submitted, expected):
        comparisons.append((submitted, expected))
        return True

    monkeypatch.setattr(config_module.hmac, "compare_digest", compare_digest)

    assert verify_judge_access_code("submitted", CONFIGURED_ENVIRONMENT) is True
    assert comparisons == [("submitted", "shared-judge-code")]


def test_deterministic_analysis_still_works_without_ai_access():
    document = normalise_pasted_source("def example(value=[]):\n    return value\n")
    state = {}

    handle_actions(state, document, analyse_clicked=True, review_clicked=False)

    assert state[ANALYSIS_KEY].syntax_valid is True
    assert state[ANALYSIS_KEY].hotspots


def test_locked_review_never_reaches_review_handler(monkeypatch):
    calls = []
    document = normalise_pasted_source("def example(value=[]):\n    return value\n")
    monkeypatch.setattr(app, "ai_access_is_granted", lambda state: False)
    monkeypatch.setattr(app, "handle_actions", lambda *args, **kwargs: calls.append(True))

    message = app.request_ai_review({}, document)

    assert calls == []
    assert message == "Unlock AI features before requesting an AI review."


def test_locked_refactor_and_alternative_never_reach_refactor_handler(monkeypatch):
    calls = []
    document = normalise_pasted_source("def example(value=[]):\n    return value\n")
    monkeypatch.setattr(app, "ai_access_is_granted", lambda state: False)
    monkeypatch.setattr(app, "handle_refactor_action", lambda *args, **kwargs: calls.append(True))

    for instructions in ("", "Try another approach."):
        message = app.request_suggested_refactor(
            {},
            document,
            optional_instructions=instructions,
            on_correction_start=lambda _: None,
        )
        assert message == "Unlock AI features before generating a suggested refactor."

    assert calls == []


def test_locked_coach_chat_never_reaches_coach_handler(monkeypatch):
    calls = []
    document = normalise_pasted_source("def example():\n    return 1\n")
    monkeypatch.setattr(app, "ai_access_is_granted", lambda state: False)
    monkeypatch.setattr(app, "handle_coach_chat_action", lambda *args, **kwargs: calls.append(True))

    app.submit_coach_question({}, document, question="Why?")

    assert calls == []


def test_incorrect_code_does_not_authorise_session():
    state = {}

    authorised = app.authorise_judge_ai_access(
        state, "wrong", verifier=lambda submitted: submitted == "shared-judge-code"
    )

    assert authorised is False
    assert state == {}


def test_correct_code_stores_only_boolean_and_persists_across_reruns():
    state = {}
    configuration = read_ai_access_configuration(CONFIGURED_ENVIRONMENT)

    authorised = app.authorise_judge_ai_access(
        state,
        "shared-judge-code",
        verifier=lambda submitted: submitted == "shared-judge-code",
    )

    assert authorised is True
    assert state == {app.JUDGE_AI_ACCESS_GRANTED_KEY: True}
    assert app.ai_access_is_granted(state, configuration) is True
    assert app.ai_access_is_granted(state, configuration) is True
    assert "shared-judge-code" not in repr(state)


def test_shared_code_authorises_independent_concurrent_sessions():
    first_session = {}
    second_session = {}

    def verifier(submitted):
        return submitted == "shared-judge-code"

    assert app.authorise_judge_ai_access(first_session, "shared-judge-code", verifier=verifier)
    assert app.authorise_judge_ai_access(second_session, "shared-judge-code", verifier=verifier)

    assert first_session == {app.JUDGE_AI_ACCESS_GRANTED_KEY: True}
    assert second_session == {app.JUDGE_AI_ACCESS_GRANTED_KEY: True}


def test_missing_or_disabled_environment_blocks_handler_calls(monkeypatch):
    review_calls = []
    refactor_calls = []
    coach_calls = []
    document = normalise_pasted_source("def example():\n    return 1\n")
    state = {app.JUDGE_AI_ACCESS_GRANTED_KEY: True}
    monkeypatch.setattr(app, "handle_actions", lambda *args, **kwargs: review_calls.append(True))
    monkeypatch.setattr(
        app, "handle_refactor_action", lambda *args, **kwargs: refactor_calls.append(True)
    )
    monkeypatch.setattr(
        app, "handle_coach_chat_action", lambda *args, **kwargs: coach_calls.append(True)
    )

    for environment in (
        {**CONFIGURED_ENVIRONMENT, "AI_ENABLED": "false"},
        {**CONFIGURED_ENVIRONMENT, "JUDGE_ACCESS_CODE": ""},
        {**CONFIGURED_ENVIRONMENT, "OPENAI_API_KEY": ""},
    ):
        for name in ("AI_ENABLED", "JUDGE_ACCESS_CODE", "OPENAI_API_KEY", "OPENAI_MODEL"):
            monkeypatch.setenv(name, environment[name])
        app.request_ai_review(state, document)
        app.request_suggested_refactor(
            state,
            document,
            optional_instructions="",
            on_correction_start=lambda _: None,
        )
        app.submit_coach_question(state, document, question="Why?")

    assert review_calls == []
    assert refactor_calls == []
    assert coach_calls == []


def _install_gate_recorder(monkeypatch, *, submitted_code: str, submitted: bool):
    calls = []

    def record(name, result=None):
        def method(*args, **kwargs):
            calls.append((name, args, kwargs))
            return result

        return method

    def form(*args, **kwargs):
        calls.append(("form", args, kwargs))
        return nullcontext()

    monkeypatch.setattr(app.st, "container", lambda **kwargs: nullcontext())
    monkeypatch.setattr(app.st, "form", form)
    monkeypatch.setattr(app.st, "markdown", record("markdown"))
    monkeypatch.setattr(app.st, "write", record("write"))
    monkeypatch.setattr(app.st, "info", record("info"))
    monkeypatch.setattr(app.st, "success", record("success"))
    monkeypatch.setattr(app.st, "error", record("error"))
    monkeypatch.setattr(app.st, "text_input", record("text_input", submitted_code))
    monkeypatch.setattr(app.st, "form_submit_button", record("form_submit_button", submitted))
    monkeypatch.setattr(app.st, "rerun", record("rerun"))
    return calls


def test_successful_unlock_does_not_render_or_retain_raw_code(monkeypatch):
    for name, value in CONFIGURED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    calls = _install_gate_recorder(monkeypatch, submitted_code="shared-judge-code", submitted=True)
    state = {}

    app.render_judge_ai_access(state)

    assert state == {app.JUDGE_AI_ACCESS_GRANTED_KEY: True}
    assert "shared-judge-code" not in repr(state)
    visible_arguments = repr(
        [(name, args, kwargs) for name, args, kwargs in calls if name != "text_input"]
    )
    assert "shared-judge-code" not in visible_arguments
    form_call = next(call for call in calls if call[0] == "form_submit_button")
    assert form_call[1][0] == "Unlock AI features"
    access_form = next(call for call in calls if call[0] == "form")
    assert access_form[2]["clear_on_submit"] is True
    password_input = next(call for call in calls if call[0] == "text_input")
    assert password_input[1][0] == "Access code"
    assert password_input[2]["type"] == "password"
    markdown = [args[0] for name, args, _kwargs in calls if name == "markdown"]
    writes = [args[0] for name, args, _kwargs in calls if name == "write"]
    assert markdown == ["### Judge AI access"]
    assert any("Deterministic analysis remains publicly available" in item for item in writes)
    assert any(name == "rerun" for name, _args, _kwargs in calls)


def test_incorrect_unlock_uses_fixed_generic_message(monkeypatch):
    for name, value in CONFIGURED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    calls = _install_gate_recorder(monkeypatch, submitted_code="wrong-secret", submitted=True)
    state = {}

    app.render_judge_ai_access(state)

    assert state == {}
    errors = [args[0] for name, args, _kwargs in calls if name == "error"]
    assert errors == ["The access code was not recognised."]
    assert "wrong-secret" not in repr(errors)


def test_disabled_switch_hides_unlock_form_and_shows_public_analysis_message(monkeypatch):
    environment = {**CONFIGURED_ENVIRONMENT, "AI_ENABLED": "false"}
    configuration = read_ai_access_configuration(environment)
    calls = _install_gate_recorder(monkeypatch, submitted_code="", submitted=False)

    assert app.render_judge_ai_access({}, configuration) is False

    info = [args[0] for name, args, _kwargs in calls if name == "info"]
    assert info == [
        "Hosted AI features are temporarily unavailable. Deterministic analysis remains available."
    ]
    assert not any(name in {"form_submit_button", "text_input"} for name, _args, _kwargs in calls)
