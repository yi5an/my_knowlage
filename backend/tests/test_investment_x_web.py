"""Tests for X Web source configuration and collector-facing APIs."""

import pytest
from pydantic import ValidationError

from app.schemas.investment import InvestmentSourceCreate


def test_x_web_account_source_normalizes_username_and_defaults_to_opinion() -> None:
    source = InvestmentSourceCreate.model_validate(
        {
            "source_type": "x_web",
            "name": "Elon Musk",
            "config": {
                "mode": "account",
                "username": "@elonmusk",
                "max_items_per_poll": 50,
            },
            "poll_interval_seconds": 900,
        }
    )

    assert source.config == {
        "mode": "account",
        "username": "elonmusk",
        "max_items_per_poll": 50,
    }
    assert source.default_info_layer == "opinion"


def test_x_web_keyword_source_preserves_query() -> None:
    source = InvestmentSourceCreate.model_validate(
        {
            "source_type": "x_web",
            "name": "Federal Reserve",
            "config": {
                "mode": "keyword",
                "query": "Federal Reserve OR 美联储",
            },
            "poll_interval_seconds": 1800,
        }
    )

    assert source.config == {
        "mode": "keyword",
        "query": "Federal Reserve OR 美联储",
        "max_items_per_poll": 50,
    }


def test_x_web_source_rejects_interval_below_five_minutes() -> None:
    with pytest.raises(ValidationError, match="at least 300 seconds"):
        InvestmentSourceCreate.model_validate(
            {
                "source_type": "x_web",
                "name": "Federal Reserve",
                "config": {"mode": "keyword", "query": "Federal Reserve"},
                "poll_interval_seconds": 299,
            }
        )


def test_x_web_source_rejects_ambiguous_config() -> None:
    with pytest.raises(ValidationError):
        InvestmentSourceCreate.model_validate(
            {
                "source_type": "x_web",
                "name": "Invalid",
                "config": {
                    "mode": "account",
                    "username": "elonmusk",
                    "query": "Federal Reserve",
                },
                "poll_interval_seconds": 900,
            }
        )
