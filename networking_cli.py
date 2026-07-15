"""Generate a daily networking review packet. This command never sends messages."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from network.networking_templates import NetworkingTarget, create_coffee_chat_prep, create_drafts


def _load_targets(value: str) -> list[dict]:
    if not value.strip():
        return []
    try:
        is_file = Path(value).exists()
    except OSError:
        is_file = False
    raw = Path(value).read_text(encoding="utf-8") if is_file else value
    data = json.loads(raw)
    return data.get("targets", []) if isinstance(data, dict) else data


def render_review_packet(targets: list[NetworkingTarget], applicant_name: str) -> str:
    lines = [f"# Networking drafts — {date.today().isoformat()}", "",
             "Review every draft before sending. Nothing in this file was sent automatically.", ""]
    for i, target in enumerate(targets, 1):
        drafts = create_drafts(target, applicant_name)
        prep = create_coffee_chat_prep(target, applicant_name)
        lines.extend([
            f"## {i}. {target.contact_name} — {target.contact_role}, {target.company}", "",
            f"Profile: {target.linkedin_url}", "", "Status: **REVIEW REQUIRED**", "",
            "### LinkedIn connection note", "", drafts["linkedin_connection_note"], "",
            "### LinkedIn follow-up", "", drafts["linkedin_follow_up"], "",
            "### Email request", "", drafts["email_request"], "",
            "### Coffee-chat request", "", drafts["coffee_chat_request"], "",
            "### Coffee-chat preparation", "",
            f"**Objective:** {prep['objective']}", "",
            f"**30-second opening:** {prep['opening']}", "",
            "**Questions:**", "",
            *[f"{number}. {question}" for number, question in enumerate(prep["questions"], 1)], "",
            f"**Value to offer:** {prep['value_to_offer']}", "",
            f"**Close:** {prep['close']}", "",
            "### Follow-up draft", "", str(prep["follow_up"]), "",
            "### Notes to capture", "",
            "- Specific insight:", "- Implication for my search/work:",
            "- Person or resource mentioned:", "- Promise I made:", "- Follow-up date:", "",
            "---", "",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", default=os.environ.get(
        "NETWORKING_TARGETS_JSON") or "config/networking_targets.example.json")
    parser.add_argument("--applicant-name", default=os.environ.get("APPLICANT_NAME", "Evan"))
    parser.add_argument("--output", default="data/daily_networking_drafts.md")
    args = parser.parse_args()
    targets = [NetworkingTarget.from_dict(item) for item in _load_targets(args.targets)]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_review_packet(targets, args.applicant_name), encoding="utf-8")
    print(f"Wrote {len(targets)} review-only networking draft set(s) to {output}")


if __name__ == "__main__":
    main()
