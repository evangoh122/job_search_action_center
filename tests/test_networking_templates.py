import pytest

from models import LinkedInPostMatch
from network.networking_templates import (
    NetworkingTarget, create_coffee_chat_prep, create_drafts,
    create_post_grounded_linkedin_draft,
)
from networking_cli import render_review_packet


def _target(**changes):
    """Provide a test helper for target."""
    values = dict(
        contact_name="Jane Tan", contact_role="Head of AI Platform", company="Acme Bank",
        linkedin_url="https://linkedin.com/in/jane", shared_context="We both work in Singapore.",
        company_signal="the bank's governed GenAI platform launch",
        relevance="I lead adoption of governed analytics products in regulated banking.",
        ask_topic="how platform teams balance reusable controls with delivery speed",
        applicant_proof="a regional data product used by 400 staff, built with Databricks",
        target_job="VP, AI Platform",
    )
    values.update(changes)
    return NetworkingTarget.from_dict(values)


def test_channel_drafts_are_specific_and_connection_note_fits_limit():
    """Verify the channel drafts are specific and connection note fits limit scenario."""
    drafts = create_drafts(_target(), "Evan")
    assert len(drafts["linkedin_connection_note"]) <= 300
    assert "governed GenAI platform" in drafts["linkedin_follow_up"]
    assert "400 staff" in drafts["linkedin_follow_up"]
    assert "not ask for a referral" in drafts["coffee_chat_request"]
    assert "20-minute" in drafts["coffee_chat_request"]
    assert "Subject:" in drafts["email_request"]
    assert "400 staff" in drafts["email_request"]


def test_coffee_chat_prep_has_opening_questions_close_and_follow_up():
    """Verify the coffee chat prep has opening questions close and follow up scenario."""
    prep = create_coffee_chat_prep(_target(), "Evan")
    assert "without asking for a referral" in prep["objective"]
    assert "400 staff" in prep["opening"]
    assert len(prep["questions"]) == 5
    assert "keep in touch" in prep["close"]
    assert "[SPECIFIC INSIGHT]" in prep["follow_up"]


def test_missing_specific_context_is_rejected():
    """Verify the missing specific context is rejected scenario."""
    with pytest.raises(ValueError, match="company_signal"):
        _target(company_signal="")


def test_review_packet_is_explicitly_unsent():
    """Verify the review packet is explicitly unsent scenario."""
    packet = render_review_packet([_target()], "Evan")
    assert "REVIEW REQUIRED" in packet
    assert "Nothing in this file was sent automatically" in packet
    assert "Email request" in packet
    assert "Coffee-chat preparation" in packet
    assert "Notes to capture" in packet


def test_post_grounded_draft_cites_actual_post_and_personal_evidence():
    """Verify the post grounded draft cites actual post and personal evidence scenario."""
    match = LinkedInPostMatch(
        id="j|p", job_id="j", job_key="k", company="Acme Bank",
        job_title="VP Data Platform", job_url="https://linkedin.com/jobs/view/1",
        post_url="https://linkedin.com/posts/1",
        post_text="We need a leader who can scale governed analytics across the region.",
        author_name="Jane Tan", confidence=1.0,
    )
    draft = create_post_grounded_linkedin_draft(
        match, "Evan", "scaling a platform to 400 users with Databricks",
        "That focus maps directly to my work in regulated banking.",
    )
    assert "Jane" in draft
    assert "scale governed analytics" in draft
    assert "400 users" in draft


def test_post_grounded_draft_blocks_generic_missing_context():
    """Verify the post grounded draft blocks generic missing context scenario."""
    match = LinkedInPostMatch(
        id="j|p", job_id="j", job_key="k", company="Acme", job_title="Role",
        job_url="https://x", post_url="https://p", post_text="Hiring", confidence=1.0,
    )
    with pytest.raises(ValueError, match="applicant_proof and relevance"):
        create_post_grounded_linkedin_draft(match, "Evan", "", "")


def test_referral_offer_draft_acknowledges_offer_without_presuming_referral():
    """Verify the referral offer draft acknowledges offer without presuming referral scenario."""
    match = LinkedInPostMatch(
        id="j|p", job_id="j", job_key="k", company="Acme", job_title="Data Lead",
        job_url="https://x", post_url="https://p",
        post_text="I am happy to refer candidates for our Data Lead opening.",
        author_name="Jane", confidence=0.9, post_intent="referral_offer",
    )
    draft = create_post_grounded_linkedin_draft(
        match, "Evan", "led a governed platform used by 400 colleagues",
        "The role maps to my regulated data-platform work.",
    )
    assert "if that offer is still current" in draft
    assert "if you think my background is relevant" in draft
    assert "refer me" not in draft.lower()
