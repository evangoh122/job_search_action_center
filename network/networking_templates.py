"""Personalized, review-only LinkedIn and coffee-chat draft generation."""
from __future__ import annotations

from dataclasses import dataclass

from models import LinkedInPostMatch


@dataclass(frozen=True)
class NetworkingTarget:
    contact_name: str
    contact_role: str
    company: str
    linkedin_url: str
    shared_context: str
    company_signal: str
    relevance: str
    ask_topic: str
    applicant_proof: str
    target_job: str = ""
    email_address: str = ""

    @classmethod
    def from_dict(cls, value: dict) -> "NetworkingTarget":
        target = cls(**{field: str(value.get(field, "")).strip()
                        for field in cls.__dataclass_fields__})
        missing = [name for name in (
            "contact_name", "contact_role", "company", "linkedin_url",
            "company_signal", "relevance", "ask_topic", "applicant_proof",
        ) if not getattr(target, name)]
        if missing:
            raise ValueError("missing personalization fields: " + ", ".join(missing))
        return target


def _first_name(name: str) -> str:
    return name.split()[0]


def create_drafts(target: NetworkingTarget, applicant_name: str) -> dict[str, str]:
    """Build channel-specific drafts; never sends or invokes a social API."""
    first = _first_name(target.contact_name)
    shared = f" {target.shared_context}" if target.shared_context else ""
    job = f" while exploring the {target.target_job} opportunity" if target.target_job else ""
    connection = (
        f"Hi {first} — your work as {target.contact_role} at {target.company} stood out, "
        f"especially {target.company_signal}. {target.relevance} I’d value connecting."
    )
    follow_up = (
        f"Hi {first}, thanks for connecting.{shared}\n\n"
        f"I reached out because {target.company_signal}. {target.relevance} "
        f"My relevant experience: {target.applicant_proof}.\n\n"
        f"I’m curious about {target.ask_topic}{job}. If it would be useful, I’d be happy "
        f"to share what I’m seeing from the practitioner side as well.\n\n{applicant_name}"
    )
    coffee_chat = (
        f"Hi {first},\n\n"
        f"I’ve been following {target.company}'s work on {target.company_signal}. "
        f"Your perspective as {target.contact_role} is particularly relevant because "
        f"{target.relevance}\n\n"
        f"I’ve worked on {target.applicant_proof}, and I’m trying to understand "
        f"{target.ask_topic} from someone close to the work—not ask for a referral. "
        f"Would you be open to a focused 20-minute coffee chat in the next two weeks? "
        f"I’ll send three questions in advance and work around your schedule.\n\n"
        f"Best,\n{applicant_name}"
    )
    email_request = (
        f"Subject: A focused question about {target.ask_topic}\n\n"
        f"Hi {first},\n\n"
        f"I am reaching out because {target.company_signal}. {target.relevance}\n\n"
        f"My closest relevant experience is {target.applicant_proof}. I would value your "
        f"perspective on {target.ask_topic}. Would you be open to a focused 20-minute call "
        f"in the next two weeks? I will send three questions beforehand and work around "
        f"your schedule.\n\nBest,\n{applicant_name}"
    )
    return {
        "linkedin_connection_note": connection[:300],
        "linkedin_follow_up": follow_up,
        "coffee_chat_request": coffee_chat,
        "email_request": email_request,
    }


def create_coffee_chat_prep(target: NetworkingTarget, applicant_name: str) -> dict[str, object]:
    """Create a factual preparation brief from the target's reviewed context."""
    return {
        "objective": (
            f"Learn how {target.contact_name} approaches {target.ask_topic}; build a useful "
            "professional relationship without asking for a referral."
        ),
        "opening": (
            f"I work on {target.applicant_proof}. I was interested in your perspective because "
            f"{target.company_signal}, and I would like to understand {target.ask_topic}."
        ),
        "questions": [
            f"What changed most in your thinking about {target.ask_topic} after doing the work?",
            f"Where does {target.company} face the hardest trade-off in this area?",
            f"What signals tell you that an initiative here is creating durable value?",
            f"Which capability is most often underestimated by people entering this work?",
            f"What would you recommend I study or test next, given {target.applicant_proof}?",
        ],
        "value_to_offer": (
            f"Offer a concise practitioner example from {target.applicant_proof}, but only if "
            "it answers their question; do not turn the chat into a pitch."
        ),
        "close": (
            "Thank them, reflect back one useful insight, ask permission to keep in touch, "
            "and confirm any resource you promised to send."
        ),
        "follow_up": (
            f"Hi {_first_name(target.contact_name)}, thank you for the conversation about "
            f"{target.ask_topic}. Your point about [SPECIFIC INSIGHT] changed how I think about "
            f"[IMPLICATION]. I will follow through on [ACTION]. As promised, here is [RESOURCE]. "
            f"I appreciated your time.\n\n{applicant_name}"
        ),
    }


def create_post_grounded_linkedin_draft(
    match: LinkedInPostMatch,
    applicant_name: str,
    applicant_proof: str,
    relevance: str,
) -> str:
    """Draft outreach that cites the matched post; reject missing personal evidence."""
    if not applicant_proof.strip() or not relevance.strip():
        raise ValueError("post-grounded outreach requires applicant_proof and relevance")
    first = _first_name(match.author_name) if match.author_name else "there"
    excerpt = " ".join(match.post_text.split())[:180].rstrip()
    referral_line = ""
    if match.post_intent in {"referral_offer", "both"}:
        referral_line = (
            " You mentioned that you may be open to referrals; if that offer is still current "
            "and if you think my background is relevant, I would appreciate learning what "
            "information you would want before considering one."
        )
    return (
        f"Hi {first}, I saw your post about {match.company}'s {match.job_title} opening. "
        f"Your note — \"{excerpt}\" — caught my attention. {relevance.strip()} "
        f"My closest relevant experience is {applicant_proof.strip()}.{referral_line} "
        "Would you be open to a focused 15-minute conversation about what the team most needs "
        f"this person to accomplish in the first six months?\n\n{applicant_name}"
    )
