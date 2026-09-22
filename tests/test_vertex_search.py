"""Tests for amlkit.screening.vertex_search -- Vertex AI Search (Discovery
Engine) adapter, substituted for the closed/sunsetting Custom Search JSON
API (see the module docstring for the citation)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from amlkit.screening.vertex_search import (
    VaisResult,
    VertexAiSearchScreener,
    serving_config_path,
)


class TestDisabledOrUnconfigured:
    def test_returns_disabled_when_env_var_absent(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMLKIT_VAIS_ENABLED", None)
            screener = VertexAiSearchScreener()
            result = screener.search("Ahmed Al Mansoori")
        assert result.status == "disabled"
        assert result.articles == []

    def test_disabled_never_constructs_a_client(self):
        def _boom():
            raise AssertionError("client_factory should never be called while disabled")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMLKIT_VAIS_ENABLED", None)
            screener = VertexAiSearchScreener(client_factory=_boom)
            screener.search("name")

    def test_returns_unconfigured_when_enabled_but_missing_project(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.delenv("AMLKIT_VAIS_PROJECT", raising=False)
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "some-engine")
        screener = VertexAiSearchScreener()
        result = screener.search("name")
        assert result.status == "unconfigured"

    def test_returns_unconfigured_when_enabled_but_missing_engine_id(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.delenv("AMLKIT_VAIS_ENGINE_ID", raising=False)
        screener = VertexAiSearchScreener()
        result = screener.search("name")
        assert result.status == "unconfigured"


class TestServingConfigPath:
    def test_builds_default_search_serving_config(self):
        path = serving_config_path("my-project", "global", "uae-news-engine")
        assert path == (
            "projects/my-project/locations/global/collections/default_collection"
            "/engines/uae-news-engine/servingConfigs/default_search"
        )

    def test_passes_through_a_fully_qualified_path(self):
        full = "projects/x/locations/global/collections/default_collection/engines/y/servingConfigs/z"
        assert serving_config_path("my-project", "global", full) == full


class TestEnabledWithMockedApi:
    def _make_result(self, link, title="", snippet=""):
        data = {"link": link, "title": title}
        if snippet:
            data["snippets"] = [{"snippet": snippet}]
        return SimpleNamespace(document=SimpleNamespace(derived_struct_data=data))

    def test_parses_results_into_articles(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "uae-news")

        pager = [
            self._make_result("https://gulfnews.com/a", "Headline A", "Snippet A"),
            self._make_result("https://thenational.ae/b", "Headline B"),
        ]
        fake_client = SimpleNamespace(search=lambda request: pager)
        screener = VertexAiSearchScreener(client_factory=lambda: fake_client)

        result = screener.search("Ahmed Al Mansoori")
        assert result.status == "ok"
        assert len(result.articles) == 2
        assert result.articles[0].url == "https://gulfnews.com/a"
        assert result.articles[0].title == "Headline A"
        assert result.articles[0].snippet == "Snippet A"
        assert result.articles[1].snippet == ""

    def test_request_uses_configured_serving_config(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "uae-news")
        monkeypatch.setenv("AMLKIT_VAIS_LOCATION", "global")

        captured = {}

        def _search(request):
            captured["request"] = request
            return []

        fake_client = SimpleNamespace(search=_search)
        screener = VertexAiSearchScreener(client_factory=lambda: fake_client)
        screener.search("query text")

        assert captured["request"].query == "query text"
        assert "uae-news" in captured["request"].serving_config

    def test_empty_query_returns_ok_with_no_results_and_no_client_call(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "uae-news")

        def _boom():
            raise AssertionError("client should not be constructed for empty query")

        screener = VertexAiSearchScreener(client_factory=_boom)
        result = screener.search("   ")
        assert result.status == "ok"
        assert result.articles == []

    def test_client_init_failure_returns_unavailable(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "uae-news")

        def _boom():
            raise RuntimeError("no credentials")

        screener = VertexAiSearchScreener(client_factory=_boom)
        result = screener.search("name")
        assert result.status == "unavailable"

    def test_search_call_failure_returns_unavailable(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "uae-news")

        def _raise(request):
            raise RuntimeError("quota exceeded")

        fake_client = SimpleNamespace(search=_raise)
        screener = VertexAiSearchScreener(client_factory=lambda: fake_client)
        result = screener.search("name")
        assert result.status == "unavailable"

    def test_result_without_link_is_skipped(self, monkeypatch):
        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_VAIS_PROJECT", "my-project")
        monkeypatch.setenv("AMLKIT_VAIS_ENGINE_ID", "uae-news")

        pager = [self._make_result("", "No link")]
        fake_client = SimpleNamespace(search=lambda request: pager)
        screener = VertexAiSearchScreener(client_factory=lambda: fake_client)
        result = screener.search("name")
        assert result.status == "ok"
        assert result.articles == []
