from __future__ import annotations

import notify_list
from notify_list import notify_company_match


def _reset():
    """Provide a test helper for reset."""
    notify_list._notify_token_sets.cache_clear()


def test_allowlist_matches_with_suffix_variants(monkeypatch):
    """Verify the allowlist matches with suffix variants scenario."""
    monkeypatch.setenv("NOTIFY_COMPANIES", "JPMorgan,DBS,Stripe,Databricks")
    _reset()
    assert notify_company_match("JPMorgan Chase") is True   # token subset
    assert notify_company_match("DBS Bank") is True
    assert notify_company_match("Stripe") is True
    assert notify_company_match("Databricks Inc") is True


def test_non_allowlisted_company_filtered(monkeypatch):
    """Verify the non allowlisted company filtered scenario."""
    monkeypatch.setenv("NOTIFY_COMPANIES", "JPMorgan,DBS")
    _reset()
    assert notify_company_match("Thunes") is False
    assert notify_company_match("Coinbase") is False


def test_empty_list_notifies_all(monkeypatch):
    """Verify the empty list notifies all scenario."""
    monkeypatch.setenv("NOTIFY_COMPANIES", "")
    _reset()
    assert notify_company_match("Anything At All") is True


def test_blank_company_not_matched(monkeypatch):
    """Verify the blank company not matched scenario."""
    monkeypatch.setenv("NOTIFY_COMPANIES", "DBS")
    _reset()
    assert notify_company_match("") is False


def test_default_file_has_seed_companies(monkeypatch):
    """Verify the default file has seed companies scenario."""
    monkeypatch.delenv("NOTIFY_COMPANIES", raising=False)
    _reset()
    # Notify-list.json ships with the seed set.
    assert notify_company_match("DBS Bank") is True
    assert notify_company_match("Some Random Co") is False
    _reset()
