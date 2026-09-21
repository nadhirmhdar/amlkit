"""Tests for BigQuery GDELT adverse media module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestGdeltBqScreener:
    def test_returns_unconfigured_when_env_var_absent(self, monkeypatch) -> None:
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        from amlkit.screening.gdelt_bq import GdeltBqScreener
        screener = GdeltBqScreener()
        result = screener.screen("Test Person")
        assert result.status == "unconfigured"
        assert result.article_count == 0

    def test_returns_results_with_mocked_bq(self, monkeypatch) -> None:
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

        mock_row1 = MagicMock()
        mock_row1.V2Themes = "TAX_FNCACT;CRISISLEX_T03_DEAD"
        mock_row1.V2Tone = "-3.5,2.1,0,0,0,0,0"
        mock_row1.SourceCommonName = "bbc.co.uk"
        mock_row1.DocumentIdentifier = "https://bbc.co.uk/news/test"

        mock_row2 = MagicMock()
        mock_row2.V2Themes = "TAX_FNCACT;CORRUPTION"
        mock_row2.V2Tone = "-1.0,1.0,0,0,0,0,0"
        mock_row2.SourceCommonName = "reuters.com"
        mock_row2.DocumentIdentifier = "https://reuters.com/article/test"

        mock_client = MagicMock()
        mock_client.query.return_value.result.return_value = [mock_row1, mock_row2]

        from amlkit.screening.gdelt_bq import GdeltBqScreener
        screener = GdeltBqScreener(client_factory=lambda p: mock_client)
        result = screener.screen("Test Person")

        assert result.status == "ok"
        assert result.article_count == 2
        assert result.avg_tone < 0
        assert len(result.theme_counts) > 0
        assert len(result.sample_sources) == 2

    def test_returns_unavailable_on_query_error(self, monkeypatch) -> None:
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

        mock_client = MagicMock()
        mock_client.query.side_effect = Exception("BQ query failed")

        from amlkit.screening.gdelt_bq import GdeltBqScreener
        screener = GdeltBqScreener(client_factory=lambda p: mock_client)
        result = screener.screen("Test Person")

        assert result.status == "unavailable"
        assert result.article_count == 0

    def test_sanitizes_name_against_injection(self, monkeypatch) -> None:
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

        mock_client = MagicMock()
        mock_client.query.return_value.result.return_value = []

        from amlkit.screening.gdelt_bq import GdeltBqScreener
        screener = GdeltBqScreener(client_factory=lambda p: mock_client)
        result = screener.screen("Test'; DROP TABLE gkg;--")

        call_args = mock_client.query.call_args
        query = call_args[0][0]
        from amlkit.screening.gdelt_bq import _sanitize_name
        sanitized = _sanitize_name("Test'; DROP TABLE gkg;--")
        assert "'" not in sanitized
        assert ";" not in sanitized
        assert result.status == "ok"


@pytest.mark.skipif(
    not __import__("os").environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="GOOGLE_CLOUD_PROJECT not set"
)
class TestGdeltBqIntegration:
    def test_real_query(self) -> None:
        from amlkit.screening.gdelt_bq import GdeltBqScreener
        screener = GdeltBqScreener()
        result = screener.screen("Donald Trump", window_days=30)
        assert result.status == "ok"
        assert result.article_count > 0
