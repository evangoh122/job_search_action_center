from linkedin_post_cli import render_packet
from models import LinkedInPostMatch


def _match():
    return LinkedInPostMatch(
        id="j|p", job_id="j", job_key="k", company="Acme Bank",
        job_title="VP Data Platform", job_url="https://linkedin.com/jobs/view/123456",
        post_url="https://linkedin.com/posts/p", post_text="We are hiring a platform leader.",
        author_name="Jane Tan", author_title="Head of Data at Acme Bank",
        author_profile_url="https://linkedin.com/in/jane", confidence=1.0,
        evidence=["exact_linkedin_job_id"], post_intent="hiring",
    )


def test_packet_contains_evidence_intent_and_grounded_draft():
    packet = render_packet(
        [_match()], "Evan", "scaled a governed platform to 400 users",
        "This is directly relevant to my regulated-bank platform work.",
    )
    assert "exact_linkedin_job_id" in packet
    assert "Intent: **hiring**" in packet
    assert "scaled a governed platform to 400 users" in packet
    assert "REVIEW REQUIRED" in packet
    assert "No connection request or message was sent" in packet


def test_packet_blocks_draft_without_personal_context():
    packet = render_packet([_match()], "Evan", "", "")
    assert "Draft blocked" in packet
    assert "generic outreach is intentionally not generated" in packet
