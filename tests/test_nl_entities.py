"""Tests for amlkit.screening.nl_entities -- Cloud Natural Language adapter."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from amlkit.screening.nl_entities import NaturalLanguageScreener, NlResult


class TestDisabledByDefault:
    def test_returns_disabled_when_env_var_absent(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMLKIT_NL_ENABLED", None)
            screener = NaturalLanguageScreener()
            result = screener.analyze("Some headline about someone.")
        assert result.status == "disabled"
        assert result.entities == []

    def test_disabled_never_constructs_a_client(self):
        def _boom():
            raise AssertionError("client_factory should never be called while disabled")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMLKIT_NL_ENABLED", None)
            screener = NaturalLanguageScreener(client_factory=_boom)
            result = screener.analyze("text")
        assert result.status == "disabled"


def _fake_entity(name, salience, score=0.0, magnitude=0.0, mid=None, type_="PERSON"):
    return SimpleNamespace(
        name=name,
        type_=SimpleNamespace(name=type_),
        salience=salience,
        sentiment=SimpleNamespace(score=score, magnitude=magnitude),
        metadata={"mid": mid} if mid else {},
    )


class TestEnabledWithMockedApi:
    def test_parses_entities_with_salience_and_sentiment(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        fake_response = SimpleNamespace(
            entities=[
                _fake_entity("Ahmed Al Mansoori", 0.42, score=-0.6, magnitude=1.2, mid="/m/0abc123"),
                _fake_entity("Dubai", 0.1),
            ]
        )
        fake_client = SimpleNamespace(
            analyze_entity_sentiment=lambda document, encoding_type: fake_response
        )
        screener = NaturalLanguageScreener(client_factory=lambda: fake_client)
        result = screener.analyze("Ahmed Al Mansoori was named in a fraud probe in Dubai.")

        assert result.status == "ok"
        assert len(result.entities) == 2
        person = result.entities[0]
        assert person.name == "Ahmed Al Mansoori"
        assert person.salience == pytest.approx(0.42)
        assert person.sentiment_score == pytest.approx(-0.6)
        assert person.sentiment_magnitude == pytest.approx(1.2)
        assert person.mid == "/m/0abc123"

    def test_entity_without_mid_metadata_has_none_mid(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        fake_response = SimpleNamespace(entities=[_fake_entity("Someone", 0.3)])
        fake_client = SimpleNamespace(
            analyze_entity_sentiment=lambda document, encoding_type: fake_response
        )
        screener = NaturalLanguageScreener(client_factory=lambda: fake_client)
        result = screener.analyze("Someone did something.")
        assert result.entities[0].mid is None

    def test_empty_text_returns_ok_with_no_entities_and_no_client_call(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")

        def _boom():
            raise AssertionError("client should not be constructed for empty text")

        screener = NaturalLanguageScreener(client_factory=_boom)
        result = screener.analyze("   ")
        assert result.status == "ok"
        assert result.entities == []

    def test_client_init_failure_returns_unavailable(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")

        def _boom():
            raise RuntimeError("no credentials")

        screener = NaturalLanguageScreener(client_factory=_boom)
        result = screener.analyze("some text")
        assert result.status == "unavailable"

    def test_api_call_failure_returns_unavailable(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")

        def _raise(document, encoding_type):
            raise RuntimeError("quota exceeded")

        fake_client = SimpleNamespace(analyze_entity_sentiment=_raise)
        screener = NaturalLanguageScreener(client_factory=lambda: fake_client)
        result = screener.analyze("some text")
        assert result.status == "unavailable"

    def test_result_is_a_plain_dataclass(self):
        result = NlResult(status="ok")
        assert result.entities == []
