from __future__ import annotations

import json
from pathlib import Path

from apply.resume_bank import load_achievements
from apply.resume_models import resume_block_hash


def test_load_achievements(tmp_path: Path):
    """Verify the load achievements scenario."""
    path = tmp_path / "achievements.json"
    path.write_text(
        json.dumps(
            [
                {
                    "keyword": "machine learning",
                    "result": "Increased revenue",
                    "metric": "$15M revenue increase",
                    "method": "enhancing model features",
                    "tags": ["ml platform"],
                }
            ]
        ),
        encoding="utf-8",
    )

    achievements = load_achievements(path)

    assert len(achievements) == 1
    assert achievements[0].keyword == "machine learning"
    assert achievements[0].tags == ["ml platform"]
    assert len(achievements[0].evidence_id) == 12


def test_load_achievements_preserves_explicit_provenance(tmp_path: Path):
    """Verify the load achievements preserves explicit provenance scenario."""
    path = tmp_path / "achievements.json"
    path.write_text(
        '[{"evidence_id":"verified-1","source":"master resume",'
        '"block_text":"Launched a governed product for 100 users.",'
        '"keyword":"data product","result":"Launched a product",'
        '"metric":"100 users","method":"building a governed workflow"}]',
        encoding="utf-8",
    )

    achievement = load_achievements(path)[0]

    assert achievement.evidence_id == "verified-1"
    assert achievement.source == "master resume"
    assert achievement.provenance == "master resume"
    assert achievement.block_hash == resume_block_hash(achievement.block_text)
    assert achievement.has_verified_master_block()


def test_load_achievements_preserves_supplied_hash_for_fail_closed_verification(tmp_path: Path):
    """A mismatched supplied hash remains detectable instead of being silently replaced."""
    path = tmp_path / "achievements.json"
    path.write_text(
        '[{"source":"master resume","block_text":"Exact block.",'
        '"block_hash":"wrong","keyword":"python","result":"Built it",'
        '"metric":"10 users","method":"using Python"}]',
        encoding="utf-8",
    )

    achievement = load_achievements(path)[0]

    assert achievement.block_hash == "wrong"
    assert not achievement.has_verified_master_block()
