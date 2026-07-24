from __future__ import annotations

import json
import hashlib
from pathlib import Path

from apply.resume_models import ResumeAchievement


def load_achievements(path: str | Path = "data/resume_achievements.json") -> list[ResumeAchievement]:
    """Load structured resume achievements from a local JSON evidence bank."""
    with Path(path).open(encoding="utf-8") as f:
        records = json.load(f)
    achievements: list[ResumeAchievement] = []
    for record in records:
        achievement = ResumeAchievement.model_validate(record)
        if not achievement.evidence_id:
            fingerprint = "\x1f".join(
                (achievement.keyword, achievement.result, achievement.metric, achievement.method)
            ).encode("utf-8")
            achievement = achievement.model_copy(
                update={"evidence_id": hashlib.sha256(fingerprint).hexdigest()[:12]}
            )
        achievements.append(achievement)
    return achievements
