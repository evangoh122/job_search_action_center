"""Tests for the exclusion gate. Positive (must exclude) + negative (must NOT)."""
import pytest

from exclusions import is_excluded_company


@pytest.mark.parametrize(
    "name",
    [
        "SMBC",
        "Sumitomo Mitsui Banking Corporation",
        "Sumitomo Mitsui Banking Corp",
        "SMFG",
        "Sumitomo Mitsui Financial Group",
        "SMBC Nikko Securities",
        "SMBC Nikko",
        "JRI",
        "Japan Research Institute",
        "The Japan Research Institute",
        "Sumitomo Mitsui Banking Corporation, Singapore Branch",  # branch variant
        "SMBC Capital Markets",
        "JRI Singapore",
    ],
)
def test_excluded(name):
    """Verify the excluded scenario."""
    assert is_excluded_company(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "JR Industries",        # contains 'jr' but is not JRI
        "Smbcorp Tech",         # contains 'smbc' substring but different company
        "Mitsui Chemicals",     # shares 'mitsui' token only
        "Research Institute of America",
        "Sumitomo Forestry",    # shares 'sumitomo' token only
        "",
    ],
)
def test_not_excluded(name):
    """Verify the not excluded scenario."""
    assert is_excluded_company(name) is False
